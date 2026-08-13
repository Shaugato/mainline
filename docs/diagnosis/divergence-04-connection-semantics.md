<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# Test-harness vs production connection semantics, and test reachability — divergence census

**Analyst:** `w4-connection-semantics` · **Measured 2026-08-13 on TRAPPOINT**, HEAD `2dc5c86`,
`.venv` pytest 9.1.1 / psycopg 3.3.4, local node CockroachDB CCL **v26.2.5** on
`127.0.0.1:26257`. Scratch world `d_w4_connection_semantics` — 271/271 migrations,
`demo_world.sql` + `demo_permit.sql` applied through `scripts/deploy/seed_demo.py`'s own
`Applier`, permit `dec0de00-0006-4000-8000-000000000001`. Every number below is the output
of a command printed beside it. **A 24-worker wave is editing this tree concurrently; where
a measurement is standing on their in-flight work I say so.**

## Verdict

Eleven connection axes enumerated and checked by execution, not by reading: **one
DIVERGENT and CRITICAL**, one DIVERGENT and HIGH, four LATENT, five HELD. The critical one
is the axis the brief named: `transitions` turns `autocommit` off on the module-scope
connection and never turns it back on, and I drove it end to end through the real handler —
after one `POST /v1/demo/gate-run`, **every subsequent GET on that warm container returns a
frozen snapshot and a byte-identical `server_date`, for the life of the container.** Four
test modules each carry the one-line repair (`conn.autocommit = True`) in their own
teardown; `mainline_demo_api/` carries it nowhere. That is this wave's defect shape at its
purest: **the harness performs the repair production is missing, so the suite cannot see
the hole.**

Reachability splits in two, and the halves disagree. **Collection is CLEAN** — the census
`docs/ci/test-collection.md` §7 prescribes passes at directory level (75 dirs) and at the
strictly stronger file level (375 files), `DIFF-EXIT=0` both times. `test_row_factory_contract.py`
and `test_refusal_row_factory.py` now execute; `scripts/qa/row_factory_ratchet.py` is **not**
dead — `tests/unit/test_row_factory_ratchet.py` runs it, 20 passed. **Enforcement is not
clean:** of the 309 demo-api tests only **139 run in any workflow**. Not one of the 18
workflows names `verticals/mainline/apps/demo-api`; the only lane that reaches them is
`ci.yml`'s `--crdb=none` job, which skips all 170 cluster-backed ones — including every
test of the four 423 guards, of the `dict_row` 500 regression suite, and of the four beats.
Widening `testpaths` made them *collectable*; nothing made them *enforced*.

---

## Inventory

`held by` = the executable mechanism that fails when the two stop agreeing, or **NOTHING**.

### A. The eleven connection axes — production vs the test-fixture families

| # | axis | production (file:line) | test fixtures (file:line) | status | held by | sev |
|---|---|---|---|---|---|---|
| 1 | `autocommit` | `db.py:306` opens `True`; `transitions.py:294`, `transitions.py:1033` set `False` and **nothing restores it** | `test_transitions.py:211` opens `False` (mutation is a no-op); `test_demo_guard_anonymous.py:168,208,326,422,500`, `test_gate_run.py:160,568`, `test_refusal_row_factory.py:124`, `test_row_factory_contract.py:582,665,692,715` all **restore `True` by hand** | **DIVERGENT** | NOTHING | **CRITICAL** (F‑1) |
| 2 | `row_factory` | `db.py:309` `dict_row` | `conftest.py:851` → the same `db.connection()`; `test_gate_run.py:295,397,483,496,593`, `test_row_factory_contract.py:336`, `test_refusal_row_factory.py:142` `tuple_row`; `conftest.py:379,384`, `test_reads.py:267,865` psycopg default | HELD | `scripts/qa/row_factory_ratchet.py` + `tests/unit/test_row_factory_ratchet.py` (20 passed) + `test_row_factory_contract.py` (15) + `test_refusal_row_factory.py` (13) | — |
| 3 | cursor-level override | `scenario.py:96` `conn.cursor(row_factory=tuple_row)` | same call | HELD — measured non-mutating: `conn.row_factory` `dict_row` before **and after** | ratchet rule `mutates_connection_row_factory` | — |
| 4 | 40001 handling, reads | `db.py:411-439`, 4 attempts, jittered backoff | **no test calls `db.read` directly and no test injects a 40001**; a single-node node never emits one (`db.py:33-34`) | LATENT | NOTHING | LOW |
| 5 | 40001 handling, writes | none by design (`db.py:43-47`); `transitions.py:1142` catches `OperationalError` → **503 `database_unreachable`** | not exercised anywhere | **DIVERGENT** | NOTHING | **HIGH** (F‑2) |
| 6 | read-only mode | `db.py:407` `SET TRANSACTION READ ONLY` per transaction | `test_reads.py:667` asserts `25006` | HELD — measured `25006` on a cold **and** on a leaked warm connection | `test_reads.py:667` | — |
| 7 | isolation level | `_prepare` `transitions.py:295`; `gate_run.py:459`; session default | fixtures inherit the session default | HELD — `SHOW transaction_isolation` = `serializable` on all six connection families | cluster default | — |
| 8 | `application_name` | `db.py:308` `mainline-demo-api` | every fixture: **empty string** | LATENT | NOTHING | LOW |
| 9 | `connect_timeout` | `db.py:307` = 10 s | `conftest.py:191` 5 s; `conftest.py:379,384,741,756,772,802` **unset**; `test_gate_run.py:106` 10 s | LATENT | `pyproject.toml:177` `timeout=120` — **and only on the root config**, see F‑4 | LOW |
| 10 | `prepare_threshold` / `prepared_max` | `db.py:303-310` sets neither → psycopg 5 / 100; a warm container **crosses** the threshold | `conftest.py:849,853` `reset_dsn_cache()` at both ends → every test gets a **fresh** connection, so **no test ever crosses it** | LATENT | NOTHING | LOW |
| 11 | driver version | `demo-api/pyproject.toml:48-49` `psycopg==3.3.4`, `psycopg-binary==3.3.4` (the Lambda artefact) | `uv.lock` resolves `psycopg>=3.2` → 3.3.4 **today**; `mainline-demo-api` is deliberately **not** a lock member (`pyproject.toml:35-38`) | LATENT | NOTHING | MEDIUM (F‑5) |

Session variables measured identical across all six connection families and therefore
**not** a divergence: `search_path` (`"$user", public`), `statement_timeout` (0),
`lock_timeout` (0), `idle_in_transaction_session_timeout` (0),
`default_transaction_read_only` (off), `default_transaction_priority` (normal), `timezone`
(UTC), `enable_implicit_transaction_for_batch_statements` (on), `session_user` (root).

### B. Reachability

| # | claim | status | held by | sev |
|---|---|---|---|---|
| 12 | every directory holding `test_*.py` is collected by a default `pytest` | **HELD**, 75/75, `DIFF-EXIT=0` | the census in `docs/ci/test-collection.md` §7 — but it is prose, invoked by no workflow and no test | LATENT |
| 13 | every test **file** (`test_*.py` **and** `*_test.py`) is collected | **HELD**, 375/375, `DIFF-EXIT=0` (a strictly stronger check than §7's) | NOTHING | — |
| 14 | the 309 demo-api tests are enforced by CI | **DIVERGENT** — 139 enforced, **170 in no workflow at all** | NOTHING | **HIGH** (F‑3) |
| 15 | one pytest configuration governs the tree | **DIVERGENT** — 15 files declare `[tool.pytest.ini_options]`; naming a path under 5 of them silently swaps the config | NOTHING | MEDIUM (F‑4) |
| 16 | `scripts/qa/row_factory_ratchet.py` (1263 lines) is invoked | **HELD** — by `tests/unit/test_row_factory_ratchet.py` (collected, 20 passed) and `test_row_factory_contract.py:195`. **Not dead.** No workflow calls it directly, and it does not need to | `tests/unit/test_row_factory_ratchet.py` | — |
| 17 | `test_row_factory_contract.py` / `test_refusal_row_factory.py` execute | **HELD** — collected and run; see §Observations for their current in-flight reds | root `testpaths` `pyproject.toml:133` | — |

---

## Findings

### F-1 `transitions` leaves `autocommit=False` on the shared connection; every GET after the first POST is frozen — severity: CRITICAL

- **Divergence:** `verticals/mainline/apps/demo-api/src/mainline_demo_api/db.py:306` opens
  the module-scope connection with `autocommit=True` · `…/transitions.py:1033` (and
  `…/transitions.py:294`) does `conn.autocommit = False` and **no line anywhere in
  `mainline_demo_api/` ever sets it back**. `…/app.py:431` hands that same object to every
  request. `…/db.py:317` (`_alive`) then runs `SELECT 1` on it, which on a non-autocommit
  connection **opens a transaction nothing ever ends**; `…/db.py:406`
  (`read_transaction`) therefore issues a `SAVEPOINT` instead of a `BEGIN`, and every read
  from then on runs inside the first post-POST transaction's snapshot.
- **Command:**

  ```
  $ .venv/Scripts/python.exe scratchpad/e2e_leak.py
    # env = exactly the three names infra/modules/demo-api/main.tf:180-187 publishes;
    # db.connection() is the only connection, as app.py:431; no pytest fixture involved.
  ```
- **Output** (verbatim, trimmed):

  ```
  ── the warm container's ONE connection ───────────────────────────────
    cold: autocommit=True  row_factory=dict_row  txn=<TransactionStatus.IDLE: 0>

  ── request 1: POST /v1/demo/gate-run  (the demo's headline beat) ────
    HTTP 200  verdict=PROVEN
    AFTER handle_transition: autocommit=False  txn=<TransactionStatus.IDLE: 0>

  ── requests 2..5: GET /v1/permit/{id}  on the same warm container ───
    GET #2: server_date=2026-08-13T07:15:55.280012Z  sees_the_change=False  txn_after=<TransactionStatus.INTRANS: 2>
      [another session committed a change to mainline.permit]
    GET #3: server_date=2026-08-13T07:15:55.280012Z  sees_the_change=False  txn_after=<TransactionStatus.INTRANS: 2>
    GET #4: server_date=2026-08-13T07:15:55.280012Z  sees_the_change=False  txn_after=<TransactionStatus.INTRANS: 2>
    GET #5: server_date=2026-08-13T07:15:55.280012Z  sees_the_change=False  txn_after=<TransactionStatus.INTRANS: 2>

    distinct server_date values across 4 GETs spanning ~3.6s of wall clock: 1

  ── what another session sees, and what the API keeps saying ─────────
    committed in the database : 'CHANGED-BY-ANOTHER-SESSION'
    GET /v1/permit contains it: False

  ── CONTROL: the same four GETs on a connection no POST has touched ──
    cold: autocommit=True
    distinct server_date values: 4
    GET /v1/permit contains the other session's change: True
  ```

  The control is the whole argument: **identical code, identical database, four distinct
  `server_date`s and the change visible — the only difference is whether a POST ran first.**
- **What a user or judge sees:** the judge runs the gate (the demo's headline act, the one
  the `/bundle/manifest.json` route hands out), then opens any of the twelve read screens.
  From that point the console is looking at a photograph. `mainline.permit`'s `head_seq`,
  the ledger's leaves, the disposition — none of it will ever change again on that
  container, no matter who commits what. And `envelope.server_date` is frozen to the
  microsecond, so `transport.ts:221-222`'s
  `clockSkewMs = Date.parse(serverDate) - clientNow` grows without bound and
  `PropagationScreen.tsx:156` — which takes `server_date` as *"the reference instant for
  every interval on this screen"* — ages every SLA on the page by real elapsed time. A
  judge who reloads after two minutes sees a two-minute clock skew against a cluster whose
  clock is fine. Because the URL carries no auth, the container is shared: **one judge's
  POST freezes the page for every judge routed to that container** until someone POSTs
  again (`_prepare`/`gate_run.py:434` roll the stale transaction back, which is why the
  symptom looks intermittent rather than permanent).
- **What would have caught it:** NOTHING DOES, and four files show why. `test_transitions.py:211`
  hands `handle_transition` a connection opened `autocommit=False`, so
  `if conn.autocommit: conn.autocommit = False` is a **no-op the test cannot observe**;
  `test_transitions.py:776 test_gate_run_leaves_the_connection_usable` then asserts only
  that `SELECT 1` still answers, which is true in both states. The three modules that *do*
  use the real `db.connection()` each repair the leak themselves, in a `finally`:

  ```
  $ grep -rnE "autocommit = (True|restore|was_autocommit)" …/demo-api/tests/*.py | wc -l
  12                    # 9 of them the literal `= True`
  $ grep -rn  "autocommit = True"  …/demo-api/src/ | wc -l
  0
  $ grep -rn  "autocommit = False" …/demo-api/src/ | wc -l
  2                     # transitions.py:294 and transitions.py:1033. Nothing undoes either.
  ```

  `test_demo_guard_anonymous.py:155-157` even writes the diagnosis down — *"Both are
  restored on the way out because `transitions._prepare` turns autocommit off and the
  connection is module-scoped and reused, exactly as it is on a warm Lambda"* — and then
  applies the fix to the fixture. `test_demo_guard_anonymous.py:226` asserts
  `anonymous_conn.autocommit is True` on a **fresh** fixture, before any transition has run.
  The last door is `conftest.py:849,853`: the `conn` fixture calls `reset_dsn_cache()`
  before *and* after every test, which drops `db._conn` — so no test in this repository
  ever sees a second request on a warm connection, and its own docstring
  (`conftest.py:846`, *"so its caching is exercised"*) claims the opposite of what those
  two lines do.
- **Fix, stated once:** `handle_transition` already documents that it *"is left with no
  transaction in progress, whatever happened"* (`transitions.py:1084-1085`). Extend that
  contract to the flag: wrap the body in `try/finally` and restore the entry value of
  `conn.autocommit`, or have `db.connection()` re-assert `autocommit=True` on every
  acquisition. The regression test must be a POST **followed by two GETs on one
  `db.connection()`**, asserting two distinct `server_date`s — no fixture may touch
  `autocommit`.

### F-2 A `40001` on any of the five POSTs is answered `503 database_unreachable` — severity: HIGH

- **Divergence:** `db.py:32-47` states, correctly, that the POST side gets no retry because
  a transition is not idempotent · `transitions.py:1142` then catches `psycopg.OperationalError`
  and returns `_error(503, "database_unreachable", …)` at `transitions.py:1148`. In psycopg
  3.3.4 `SerializationFailure` **is** an `OperationalError`, so SQLSTATE `40001` lands in
  the branch whose own comment (`transitions.py:1143-1145`) says it exists to keep *"the
  gate did not refuse"* and *"there was nothing to ask"* apart. A serialization restart is
  neither.
- **Command:**

  ```
  $ .venv/Scripts/python.exe scratchpad/post40001.py
    # injects the verbatim Cloud message db.py:37-39 records from the 2026-08-10 run
  ```
- **Output:**

  ```
  psycopg class hierarchy for SQLSTATE 40001:
     Exception -> Error -> DatabaseError -> OperationalError -> SerializationFailure
     issubclass(SerializationFailure, psycopg.OperationalError) = True

  POST /v1/demo/gate-run when the cluster answers 40001:
     HTTP 503   error='database_unreachable'
     detail = restart transaction: TransactionRetryWithProtoRefreshError: TransactionRetryError: retry txn (RETRY_SERIALIZABLE - failed preemptive refresh)
     connection left: autocommit=False txn=<TransactionStatus.IDLE: 0>
  ```
- **What a user or judge sees:** Cloud `mainline_demo` is a managed multi-node cluster and
  the wave brief already names *"needs a 40001 retry loop"* as a platform fact; `db.py:35-39`
  records that the deployment lead's **first** Cloud run died on exactly this SQLSTATE. The
  URL has no auth, so two judges pressing a beat within the same instant is the ordinary
  case. One of them gets `503 database_unreachable` — a sentence that is false (the
  database answered) and unactionable (retrying immediately would have worked). Anyone
  triaging goes looking at the cluster, at Terraform, at the SSM parameter, at the VPC.
- **What would have caught it:** NOTHING DOES, and it is structurally impossible for the
  present suite to. A single-node Docker cluster never produces `RETRY_SERIALIZABLE`
  (`db.py:33-34`, restated at `test_gate_run.py:389`), so the only cluster the suite ever
  meets cannot emit the error. No demo-api test injects one either:

  ```
  $ grep -rn "SerializationFailure\|40001" verticals/mainline/apps/demo-api/tests/*.py
  conftest.py:30,305,437      (prose, about the seeder's loop)
  test_gate_run.py:383,389,400  (the FIXTURE's own receipt-reissue retry, not the API's)
  $ grep -rn "READ_RETRY_ATTEMPTS\|db\.read(" verticals/mainline/apps/demo-api/tests/*.py
  (no output)
  ```

  So `db.read`'s four-attempt loop (`db.py:423`) — the one thing `db.py`'s docstring says
  exists because Cloud died without it — has **never had its retry branch taken by
  anything**. The fix is a unit test that injects a `SerializationFailure` at the boundary,
  and a separate `_error(503, "transaction_retry", …)` (or a 409) for SQLSTATE class 40, so
  the two findings stay apart.

### F-3 170 of the 309 demo-api tests run in no workflow — severity: HIGH

- **Divergence:** `pyproject.toml:133` collects `verticals/*/apps/demo-api/tests` ·
  **no workflow names that directory.** The only lane that reaches it is
  `.github/workflows/ci.yml:441` `hermetic-tests`, whose two pytest steps
  (`ci.yml:487`, `ci.yml:523`) pass `--crdb=none`, which makes `conftest.py:294` skip every
  `requires_cluster` item.
- **Command and output:**

  ```
  $ grep -rn "demo-api\|demo_api" .github/workflows/
  .github/workflows/demo-health.yml:56:#      `mainline_demo_api.gate_run`; this job compares and never composes.
        ← one comment. No workflow runs these tests by path.

  $ pytest -c pyproject.toml --crdb=none -q verticals/mainline/apps/demo-api/tests
  139 passed, 170 skipped in 11.77s
  SKIPPED [170] conftest.py:294: the session obtained no CockroachDB, so this cluster-backed
    test is skipped rather than allowed to reach a node the session declined to obtain.

  $ pytest -c pyproject.toml --crdb=none --co -q -m requires_cluster verticals/…/demo-api/tests
    10 test_credentials.py
    13 test_demo_guard_anonymous.py     ← the four 423 guards, entire
    21 test_gate_run.py                 ← the four beats, entire
    74 test_reads.py                    ← all twelve read resources, entire
    13 test_refusal_row_factory.py      ← the dict_row-500 regression suite, entire
    15 test_row_factory_contract.py     ← ditto
    24 test_transitions.py              ← the five POSTs, entire

  $ pytest -c pyproject.toml --crdb=none --co -q -m "g4alpha or pl2_red" verticals/…/demo-api/tests
  no tests collected (309 deselected)      ← `red-by-design` (ci.yml:634) covers none of them
  ```
- **What a user or judge sees:** the same class of failure as the last three NO-GOs,
  arriving the same way. A change that breaks the anonymous-423 lane, the four beats, the
  twelve reads, or the `dict_row` contract passes CI green — the tests written to catch it
  are collected, counted in the 9670, reported as `skipped`, and never run against a
  database. `docs/ci/test-collection.md` §6 already records the only measurement that has
  ever exercised them: a **laptop** invocation.
- **What would have caught it:** NOTHING DOES. The mechanism exists three doors down —
  `db.yml`, `db-schema.yml`, `schema.yml`, `custody-chain.yml` and `release-proof.yml` all
  stand a CockroachDB up and run cluster-backed tests against it; the demo-api is simply not
  wired into any of them. Wiring it in is one job, and it is the single highest-value change
  a subsequent wave can make to this repository's ability to catch its own defects: **F-1
  and F-2 are both in that unenforced 170.**

### F-4 Naming a path under 5 of the 15 pytest configs silently swaps the config — severity: MEDIUM

- **Divergence:** `pyproject.toml:129-201` declares `timeout = 120`,
  `timeout_method = "thread"`, `filterwarnings = ["error", …]`, `--strict-config` and 17
  markers · `verticals/mainline/apps/demo-api/pyproject.toml:77-82` declares its own
  `[tool.pytest.ini_options]` with none of them. pytest resolves rootdir from the
  arguments' common ancestor, so `pytest verticals/mainline/apps/demo-api/tests` — run
  **from the repository root** — takes the app's config, not the root's.
- **Command:** `.venv/Scripts/python.exe scratchpad/ini_diff2.py` (a `pytest_configure`
  plugin printing the effective ini for five real invocation routes)
- **Output:**

  ```
  === CI: bare `pytest` from the root (testpaths) ===
    configfile     pyproject.toml
    timeout        '120'   timeout_method 'thread'
    filterwarnings ['error', 'default::DeprecationWarning', …]
    addopts        ['--strict-markers', '--strict-config', '-ra']
    markers(17)    ['requires_cluster', 'requires_aws', 'g4alpha', 'pl2_red', 'slow', 'schema'] ...
    9670 tests collected

  === named path under the app, from the root ===
    configfile     verticals\mainline\apps\demo-api\pyproject.toml
    timeout        ''   timeout_method ''
    filterwarnings []
    addopts        ['--strict-markers', '-ra']
    markers(5)     ['requires_cluster', 'requires_cluster', 'timeout(…)', 'hypothesis', 'anyio']
    309 tests collected

  === named path under tests/ ===
    configfile     pyproject.toml          ← the same shape of command KEEPS the root config
  ```

  And the same probe across every `pytest <path>` a workflow actually runs
  (`scratchpad/wf_ini.py`):

  ```
  ci.yml:487/523               ROOT CONFIG                              9670 collected
  custody-chain.yml:116        ** packages\trappoint-jcs\pyproject.toml **       82   timeout '120'->''; filterwarnings=error LOST; --strict-config LOST; markers 17->4
  custody-chain.yml:139        ** packages\trappoint-ledger\pyproject.toml **   285   (same)
  custody-chain.yml:440        ** packages\trappoint-verify\pyproject.toml **    95   (same)
  db-schema.yml:108            ** packages\trappoint-migrate\pyproject.toml **  300   (same)
  boundary.yml:161/352, custody-chain.yml:1157/1293/1311,
  mutation-ratchet.yml:388, nightly-differential:341,
  release-proof.yml:289, schema.yml:483                ROOT CONFIG
  ```
- **What a user or judge sees:** 762 tests in four CI steps run with **no 120-second
  timeout** and **no warnings-as-errors**. `pyproject.toml:176-192` explains at length that
  the timeout exists because *"a test that hangs is a test that has stopped asserting"* and
  because `timeout_method = "thread"` is the only method that works on Windows — and
  `docs/ci/test-collection.md` §4 records a run that *"died at 99%, after twelve minutes"*
  precisely because a newly-collected suite hung. In those four steps the guard is absent,
  so the failure mode is a 12-minute job timeout with no stack naming a fixture.
  Independently: `docs/ci/test-collection.md` §1's headline numbers were taken on the
  swapped config (no `-c`), while §5 and §6 pass `-c pyproject.toml`; the two halves of that
  document are not measuring the same harness.
- **What would have caught it:** NOTHING DOES. Today the divergence is only in the *global*
  settings, because the only markers the demo-api uses are `requires_cluster` and
  `parametrize` (`grep -rhoE "@pytest\.mark\.[a-z_0-9]+" …/demo-api/tests` → `14 parametrize,
  9 requires_cluster`). Add one `@pytest.mark.slow` and `--strict-markers` turns the
  standalone route into a **hard collection error** while the root route stays green.
  Cheapest closure: delete the four redundant keys from
  `verticals/mainline/apps/demo-api/pyproject.toml:77-82` (they only shadow the root), or
  have the census script assert that `config.inipath` is the repository root for every path
  a workflow names.

### F-5 The Lambda pins `psycopg==3.3.4`; the suite runs on whatever `uv.lock` resolved — severity: LATENT (MEDIUM if it moves)

- **Divergence:** `verticals/mainline/apps/demo-api/pyproject.toml:47-50` pins
  `psycopg==3.3.4` / `psycopg-binary==3.3.4` and its comment shows the exact
  `pip install --platform manylinux2014_x86_64` line the deployment package is built with ·
  `uv.lock`'s only constraint on psycopg is `{ name = "psycopg", extras = ["binary"],
  specifier = ">=3.2" }`, inherited from a workspace member. `mainline-demo-api` is
  **deliberately not** a lock member (`pyproject.toml:35-38`, and the comment says why), so
  its `==` pin participates in no resolution CI performs.
- **Command and output:**

  ```
  $ awk '/^\[\[package\]\]/{p=0} /name = "psycopg"$/{p=1} p' uv.lock | head -3
  name = "psycopg"
  version = "3.3.4"
  $ .venv/Scripts/python.exe -c "import psycopg; print(psycopg.__version__)"
  3.3.4
  ```
- **What a user or judge sees:** nothing today — the two agree. They agree because `>=3.2`
  resolved to the newest release and the newest release happens to be the pinned one. The
  next `uv lock` after psycopg publishes 3.4 moves CI to 3.4 and leaves the Lambda on 3.3.4,
  and *the driver is the connection*: `row_factory`, `Transaction`/`SAVEPOINT` emission,
  `prepare_threshold`, and SQLSTATE-to-exception mapping are all its behaviour, and F-1 and
  F-2 above are both consequences of exactly those. A whole-class divergence would open with
  no diff in this repository at all.
- **What would have caught it:** NOTHING DOES. A three-line test asserting that the
  demo-api's pinned version equals the version `uv.lock` resolves would hold it; the
  repository already has the pattern in `scripts/qa/check_workspace_members.py`.

### F-6 `application_name` is set in production and by no fixture — severity: LOW / LATENT

- **Divergence:** `db.py:86` declares `APPLICATION_NAME = "mainline-demo-api"` with the
  stated purpose *"A judge watching the cluster while they drive the demo can see which
  sessions are ours"*, applied at `db.py:308` · every test fixture that opens its own
  connection (`conftest.py:191,379,384,741,756,772,802`, `test_gate_run.py:295,397,443,453,469,483,496,593`,
  `test_reads.py:267,860,865,895`, `test_transitions.py:211,220,238,396`, `test_credentials.py:147,177,200,219,236,272`,
  `test_demo_guard_anonymous.py:145,182,244`, `test_row_factory_contract.py:227,245,252,268,281,336`)
  passes none, so `SHOW application_name` returns `''`.
- **Command and output** (`scratchpad/axes.py`, all six families):

  ```
  PRODUCTION db.connection()                       application_name = "mainline-demo-api"
  psycopg.connect(dsn, autocommit=True)            application_name = ""
  psycopg.connect(dsn, autocommit=True, dict_row)  application_name = ""
  psycopg.connect(dsn, autocommit=False, tuple_row) application_name = ""
  psycopg.connect(dsn, connect_timeout=5, …)       application_name = ""
  ```
- **What a user or judge sees:** the claim in `db.py:85-86` is the only one on this axis and
  it is untested; if the kwarg were dropped the demo would work and nobody would learn until
  a judge looked at `SHOW SESSIONS` and could not tell our sessions apart. Note also
  `test_reads.py:663` appends `&application_name=w3-other` to the DSN to force a
  cache-replacement — the one place a fixture touches this axis, and it does so to test
  something else.

---

## Pairs checked and found to agree, with the mechanism that holds them

* **`row_factory`.** `db.py:309` `dict_row` against every statement in the package. Held by a
  live three-layer mechanism: the rule in `scripts/qa/row_factory_ratchet.py`, imported
  rather than restated by `test_row_factory_contract.py:195`, and run repo-wide by
  `tests/unit/test_row_factory_ratchet.py` — `pytest tests/unit/test_row_factory_ratchet.py`
  → `20 passed in 9.83s`. **The ratchet is not dead and is not workflow-orphaned**: it is
  enforced through the pytest lane, which is the stronger place for it. It is *currently*
  red on an in-flight module (see Observations), which is the ratchet doing its job.
* **`scenario.positional` does not mutate the connection.** Measured:
  `conn.row_factory` is `dict_row` before the call and `dict_row` after, `unchanged=True`.
  The ratchet carries a rule named `mutates_connection_row_factory` for this.
* **`SET TRANSACTION READ ONLY` still binds on a leaked warm connection.** I expected this to
  be a second finding and it is not. Measured on both a cold and an `INTRANS` warm
  connection: `SHOW transaction_read_only -> 'on'` and the write refused
  `[25006] cannot execute UPSERT in a read-only transaction`. Held by `test_reads.py:667`.
* **A failing read does not poison a warm connection.** Also expected and also absent:
  psycopg's `Transaction` fences the failure with `ROLLBACK TO SAVEPOINT`, so read #3 and
  #4 after a `42P01` both succeed on cold **and** on leaked-warm connections.
* **The leftover read-only transaction does not break the next POST.** `_prepare`
  (`transitions.py:295`) and `gate_run.py:434` each `rollback()` first, so a POST arriving
  after a GET on a leaked connection is not refused `25006`. This is the one place the
  existing code accidentally contains F-1's repair, and it is why F-1 presents as
  intermittent staleness rather than as a hard failure.
* **Prepared statements accumulate harmlessly.** 40 identical `/v1/permit` GETs on one warm
  connection: `0 error(s)`, 7 server-side prepared statements. Nothing holds this — no test
  crosses `prepare_threshold` — but nothing is wrong with it today.
* **Session variables.** `search_path`, `statement_timeout`, `lock_timeout`,
  `idle_in_transaction_session_timeout`, isolation, priority, timezone, `session_user`:
  identical across all six connection families. Held by the cluster's defaults, which is to
  say by NOTHING in this repository — but there is no divergence to report.
* **Test collection.** Both censuses pass:

  ```
  $ diff <(git ls-files --cached --others --exclude-standard -- '*/test_*.py' 'test_*.py' \
            | xargs -n1 dirname | sort -u) \
         <(pytest --collect-only -q | grep '::' | sed 's/::.*//' | xargs -n1 dirname | sort -u)
  DIFF-EXIT=0   dirs=75
  # the stronger form, per FILE and including the `*_test.py` naming convention:
  DIFF-EXIT=0   files=375
  ```
  Held by the census in `docs/ci/test-collection.md` §7 — which is a paragraph in a document,
  run by no workflow and no test. Recommend promoting it to `tests/release/`.

---

## Observations that belong to other analysts (cross-references, not my findings)

1. **The demo-api suite is red right now, and it is the concurrent wave's in-flight work.**
   `pytest --crdb=reuse -q verticals/mainline/apps/demo-api/tests` →
   `4 failed, 241 passed, 1 skipped, 63 errors in 74.04s`. `git diff --stat` shows
   `tests/conftest.py` `927 ++---` mid-rewrite (the "one world" fix, replacing the parallel
   fixture world with `demo_world.sql`). All 63 errors are one cause —
   `KeyError: "'cr_id' is not an identifier the deployed demo seed produces"` at
   `conftest.py:415`, raised for `test_reads.py:90` — i.e. **the deployed demo carries no
   `mainline.change_request`, and `/v1/change-request/{cr_id}` has no row to serve.** That is
   W1/W5's; I record it because it is the fixture *working*, and because it means the
   twelve-resource read surface is eleven.
2. **`test_refusal_row_factory.py::test_the_declined_branch_…` and `…savepoint_fence…`**
   fail because the constraint they picked as un-explainable is now explainable in
   `demo_world.sql`'s world. Same root cause as (1). W6's.
3. **`test_row_factory_contract.py::test_every_module_…_named_row_convention`** is red on
   `{'credentials.py': 'position'}` — a module the concurrent wave added minutes ago and
   has not yet added to the enumeration table. **This is the ratchet catching a new module
   the moment it lands**, which is the property it was written for.
4. **Four demo-api test modules still build their world from
   `scripts/proof/gate_refusal.py::seed_history`, not from `demo_world.sql`.**
   `test_gate_run.py:412` (`w4_database`), `test_row_factory_contract.py:238` (`w1_database`,
   external ref `PTW-PROOF-1`), and the modules that consume them —
   `test_transitions.py`, `test_demo_guard_anonymous.py`. The shared `conftest.py` was
   rewritten to close exactly this gap and these four did not follow. **That is the beat-4
   FK defect's own mechanism, still standing in 73 of the 309 tests.** W1's slice, flagged
   here because the root cause is mine: *the test ran against a world production never uses.*
5. **The hardcoded DSN fallbacks are still in the tree** — `test_gate_run.py:106` and
   `test_row_factory_contract.py:104`, both `postgresql://root@127.0.0.1:26257/defaultdb…`,
   as `docs/ci/test-collection.md` §8.1 says. They are now harmless *for a session*
   (`conftest.py:285-298`'s `pytest_runtest_setup` skips the items first — measured, 170
   skips, one named reason) but the fallback itself is unguarded for anything that reaches
   it outside a `requires_cluster` item.

## Not reached (and why)

* **CockroachDB Cloud `mainline_demo`.** Every axis above was measured against the local
  v26.2.5 node. Axes 1–3, 5, 8, 10 and 11 are properties of the client and carry over
  unchanged; axes 6, 7 and the session variables are cluster-side and a Cloud Basic cluster
  could differ (in particular a Cloud-side `statement_timeout` or a different
  `default_transaction_isolation`). Re-measuring `axes.py` against the Cloud DSN is one
  read-only command and would close the remaining doubt. It is also the only environment in
  which F-2 can be observed naturally.
* **A real `40001` from the local node.** `crdb_internal.force_retry` is refused
  (`[42501] Access to crdb_internal and system is restricted`), so F-2 was proven by
  injecting `psycopg.errors.SerializationFailure` at the boundary and by the class
  hierarchy, not by a natural conflict. The classification result does not depend on how the
  exception arose.
* **The other 10 slices' subject matter.** Deliberately not touched.
