<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# The demo-api suite in more than one order — seeds, isolation, and what it costs

**Worker:** W5, demo-suite wave · **Measured 2026-08-13 on TRAPPOINT**, against the working
tree at `D:/CoackroachDBxAWS/mainline` (HEAD `073dfea` plus this wave's uncommitted work),
with `.venv/Scripts/python.exe` — Python 3.13.14, pytest 9.1.1, psycopg 3.3.4, `win32`,
CockroachDB CCL **v26.2.5** in container `trappoint-crdb`.

Every number below is the output of a command printed beside it, taken from the JUnit XML
rather than from a terminal scroll. The harness is
[`scripts/qa/demo_suite_order.py`](../../scripts/qa/demo_suite_order.py); no pytest plugin
was added and `uv.lock` is untouched, because `uv lock --check` in `ci.yml` is what makes
"a stranger resolves the same dependency graph" true and a shuffle is `random.Random(seed)`.

> ### Read this before comparing any two totals in this file
>
> **This wave ran six workers against one laptop, one CockroachDB node and one working
> tree, concurrently.** `verticals/mainline/db/seeds/demo/demo_world.sql` was rewritten by
> another worker at `00:18` — in the middle of a five-seed battery — and
> `tests/conftest.py::_fingerprint()` hashes the seed files, so **every edit renames the
> shared fixture database and forces a rebuild**. Measured across one twenty-minute
> A/B: the fingerprint went `885e1182f4e6 → 0ecbb18f3666 → 885e1182f4e6`, and the same
> suite reported `63 errors`, then `104 errors`, then `105 skips`, then `63 errors` again —
> **with no change to any file this worker owns**.
>
> So the four numbers of any single run in this wave are a statement about *when* it ran.
> Everything in this file is therefore either (a) taken from one contiguous window with the
> tree hash recorded, or (b) a **within-run** comparison — a named family of failures
> present in one arm and absent in the other — which is invariant to the world churning.
> §1.6 is the load-bearing evidence and is of kind (b) on purpose.

---

## 0 · The headline, in four sentences

1. **The 503 test is order-dependent, and the order that breaks it is three node ids long.**
   `test_transitions::test_the_request_after_a_gate_run_is_not_a_503` is green in file order
   and `assert 422 == 200` in an interleaved one. The orchestrator and the lead were both
   telling the truth about different orders. **Settled, reproduced, and fixed.**
2. **The cause was two session-scoped fixtures publishing the same four environment
   variables for two different databases.** Fixed by scoping the *publication* to the test
   that asked for the database, while the expensive *build* stays session-scoped.
3. **After the fix, five random orders and all fourteen modules run alone produce results
   identical to file order, test for test.** Before it, two of two seeds produced six extra
   failures.
4. **The suite is not slow; the DSN is.** `localhost` resolves to `::1` first on this host,
   the container publishes IPv4 only, and every connection therefore burns the full 10 s
   `connect_timeout` before falling back. Spelling the same node `127.0.0.1` takes the
   suite from **1 558 s to 66 s**, and moves exactly three outcomes — one of which is
   W2's ten-second `/v1/health`, which turns out not to be a `health.py` defect at all
   (§5.1).

---

## 1 · The 503 test, settled

### 1.1 · What was in dispute

The wave brief recorded
`test_transitions::test_the_request_after_a_gate_run_is_not_a_503` as **failing**. The
lead's own full-suite run at the same HEAD recorded it **passing**
(`out/demo-suite-baseline.xml`, §0.2 of `docs/leads/demo-suite-plan.md`). My own
whole-suite run recorded it **passing** as well. One run cannot settle this, because
"the suite" is not an experiment — the order is.

### 1.2 · The mechanism, measured

Two session-scoped fixtures build two different scratch databases and both write the same
four process environment variables:

| fixture | file | database | `PTW-PROOF-1` permit | site |
|---|---|---|---|---|
| `w4_database` | `tests/test_gate_run.py:450` | `w_w4_api_transitions` | `199adc10-e49d-429c-910b-a872d2baa77c` | `8d78a33e-…` |
| `w1_database` | `tests/test_row_factory_contract.py:254` | `w_w1_rowfactory` | `44070eee-a807-4a71-93d2-6dfd56965bd2` | `7c2495e6-…` |

```
$ SELECT permit_id, site_id, state FROM mainline.permit WHERE external_ref='PTW-PROOF-1'
w_w4_api_transitions   199adc10-e49d-429c-910b-a872d2baa77c   8d78a33e-…   dispositioned
w_w1_rowfactory        44070eee-a807-4a71-93d2-6dfd56965bd2   7c2495e6-…   dispositioned
```

They differ because `scripts/proof/gate_refusal.py::seed_history` mints `uuid.uuid4()` for
the site and the permit on every seeding — correctly, one world per database. Both
fixtures then do this, and restore only at **session** teardown:

```python
os.environ["MAINLINE_DEMO_PERMIT_ID"] = str(permit_id)   # + SITE_ID, SIGNER_SUB, COUNTERSIGNER_SUB
```

`scenario.from_env()` reads those names at call time, and `scenario.resolve()` raises
`ScenarioNotSeeded` when the permit is not in the connection's database. So **whichever
fixture set up last owned those four names for the rest of the session**, and any test
after it that combined the environment with the *other* database was describing one
database while talking to another.

Two more facts make the timing unpredictable rather than merely wrong. `w4_database` is
imported into `test_demo_guard_anonymous.py` and `test_transitions.py`
(`from test_gate_run import w4_database`), and pytest gives an imported fixture a **fresh
`FixtureDef` per importing module** — so its body runs three times in a full session, and
each run re-publishes the environment. Measured with a throwaway `pytest_fixture_setup`
hook wrapper:

```
[FIXWATCH] fixture w4_database (scope=session)  MAINLINE_DEMO_PERMIT_ID: None       -> 199adc10-…
[FIXWATCH] fixture w1_database (scope=session)  MAINLINE_DEMO_PERMIT_ID: 199adc10-… -> 44070eee-…
[FIXWATCH] fixture w4_database (scope=session)  MAINLINE_DEMO_PERMIT_ID: 44070eee-… -> 199adc10-…
```

That third line is why the test is green in file order: `test_transitions.py`'s *own copy*
of `w4_database` happens to re-point the environment back at the moment its first test
runs. It is an accidental repair, and it holds only while no `test_row_factory_contract`
test lands between two `test_transitions` tests.

### 1.3 · The reproduction — three node ids, 0.68 s

`out/order/probe-interleave.args`:

```
verticals/mainline/apps/demo-api/tests/test_transitions.py::test_the_shared_connection_is_the_one_db_py_opens
verticals/mainline/apps/demo-api/tests/test_row_factory_contract.py::test_the_production_connection_really_is_dict_row
verticals/mainline/apps/demo-api/tests/test_transitions.py::test_the_request_after_a_gate_run_is_not_a_503
```

```
$ pytest @out/order/probe-interleave.args --crdb=reuse -q
..F
test_transitions.py:919: in test_the_request_after_a_gate_run_is_not_a_503
    assert handle_transition("demo_gate_run", {}, {"run_id": "w7-then-next"}, shared_conn)[0] == 200
E   assert 422 == 200
1 failed, 2 passed in 0.68s
```

The 422 is `demo_history_not_seeded`: `w1_database` published its permit, and
`shared_conn` is open on `w_w4_api_transitions`.

**The same defect, in the other direction, under a printed seed.** Before the fix,
`demo_suite_order.py shuffle --seed 7` and `--seed 20260813` each turned six tests **in
`test_row_factory_contract.py`** red with

```
mainline_demo_api.scenario.ScenarioNotSeeded: no mainline.permit with permit_id
199adc10-e49d-429c-910b-a872d2baa77c in this database.
```

— w4's permit, looked for in w1's database. So the failure lands in whichever module the
scheduler happens to put second, which is exactly why it reads as folklore.

### 1.4 · The verdict

> **`test_the_request_after_a_gate_run_is_not_a_503` was neither reliably green nor
> reliably red. It was order-dependent.** Both earlier observations were correct
> measurements of different orders. As of this change it is green in file order, in five
> printed seeded orders, and in module isolation.

### 1.5 · The fix, and what it deliberately is not

`tests/test_row_factory_contract.py` now separates the two lifetimes:

* **`_w1_built`** — `scope="session"`. Builds or adopts `w_w1_rowfactory` (271 migrations,
  ~50 s when it must build), reads its subject back out with the readiness query it already
  ran, and returns `(dsn, permit_id, site_id)`. **Touches no environment variable.**
* **`w1_database`** — function-scoped. Points the four `MAINLINE_DEMO_*` names at those
  identifiers for the duration of **one test** and restores the previous values in a
  `finally`. It opens no connection: a re-read here would cost one round trip per test —
  0.23 s over IPv4 and **10.2 s** over a `localhost` DSN (§5.1) — to re-derive four strings
  the session already has.

Every consumer (`production_conn`, `tuple_conn`) keeps its signature; the diff is
**53 insertions, 4 deletions**, and 44 of the insertions are the docstring above. The build
is still paid once per session.

**What this is not.** It is not an order pin. No test was reordered, no dependency marker
was added, no file was renamed to sort differently, and no assertion, ceiling, fixture
constant or expected value was moved. An order pin would be a green that certifies itself;
what changed is the leaking state.

**Falsification, done by hand and reverted.** `test_row_factory_contract.py` was edited to
put the four `os.environ` assignments back inside the session-scoped builder (marked
`# <-- PLANTED DEFECT`), and:

```
$ pytest @out/order/probe-interleave.args                 ->  1 failed in 0.44s
                                                              assert 422 == 200
                                                              test_transitions.py:919
$ pytest @out/order/w5-seed-7.args                        ->  25 failed, 435 passed, 63 errors
      of which 6 are ScenarioNotSeeded in test_row_factory_contract — the original family —
      plus 19 more, because the plant never un-publishes at all and so is strictly stronger
      than the defect it re-creates.
```

The file was then restored byte-for-byte from the pre-plant copy
(`sha256 cb8fae6affdf…`, `grep -c PLANTED → 0`, `ruff check` clean, 15/15 green). A
falsification harness that leaves a defect behind is worse than none.

### 1.6 · The A/B, run back to back, immune to the churn

The only file W5 changed, swapped between `git show HEAD:…` and this worker's version, in
one twenty-minute window, with private scratch databases
(`MAINLINE_W1_DATABASE=w_w5_order_w1`, `MAINLINE_W4_DATABASE=w_w5_order_w4`). The world
changed under it three times — which is why the column that matters is not the totals but
the **named failure family**:

| arm | order | fingerprint | tests / F / E / s | `ScenarioNotSeeded` failures |
|---|---|---|---|---:|
| `HEAD` | file order | `885e1182f4e6` | 524 / 7 / 63 / 1 | **0** |
| `HEAD` | seed `20260813` | `0ecbb18f3666` | 524 / 11 / 104 / 1 | **6** |
| `HEAD` | seed `7` | `0ecbb18f3666` | 524 / 11 / 0 / 105 | **6** |
| **W5** | file order | `0ecbb18f3666` | 524 / 5 / 104 / 1 | **0** |
| **W5** | seed `20260813` | `0ecbb18f3666` | 524 / 5 / 0 / 105 | **0** |
| **W5** | seed `7` | `885e1182f4e6` | 524 / 7 / 63 / 1 | **0** |

Six order-induced failures in **every** seeded run of `HEAD`'s file, zero in **every**
seeded run of this worker's, across three different worlds. And the first and last rows are
the same world by fingerprint: `HEAD` **in file order** and W5 **in a shuffled order**
produce byte-identical totals — which is the property the whole exercise is for.

---

## 2 · Five seeds

`scripts/qa/demo_suite_order.py shuffle` collects with `pytest --collect-only -q`,
shuffles under a printed seed, writes the order to `out/order/w5-seed-<n>.args`, and runs
`pytest @<file>`. The **seed and the file are both printed**, and printed again on failure:
a seed reproduces the order only while collection and the shuffling algorithm are
unchanged, whereas the file reproduces it forever.

All six runs below are the **final** battery: one contiguous window, the FINAL code, private
scratch databases (`MAINLINE_W1_DATABASE=w_w5_order_w1`,
`MAINLINE_W4_DATABASE=w_w5_order_w4`), and the tree fingerprint **sampled at both ends and
unchanged** — `885e1182f4e6` before the first run and after the last. That is what licenses
comparing these six totals to each other; §1.6 is what makes the finding survive an edit.

| seed | tests | passed | failed | skipped | errors | seconds | same result as file order? |
|---|---:|---:|---:|---:|---:|---:|---|
| *(file order, control)* | 524 | 453 | 7 | 1 | 63 | 44.1 | — |
| `20260813` | 524 | 453 | 7 | 1 | 63 | 43.8 | **identical, test for test** |
| `7` | 524 | 453 | 7 | 1 | 63 | 45.9 | **identical, test for test** |
| `41` | 524 | 453 | 7 | 1 | 63 | 44.8 | **identical, test for test** |
| `1729` | 524 | 453 | 7 | 1 | 63 | 45.8 | **identical, test for test** |
| `99991` | 524 | 453 | 7 | 1 | 63 | 46.1 | **identical, test for test** |

```
$ py - <<'PY'   # the set comparison behind the last column
ALL FIVE SEEDS IDENTICAL TO FILE ORDER: True | non-passing: 71
PY
```

An earlier battery in the 23:52–00:05 window, against the first draft of the same fix and
shared scratch databases, produced the same six rows at 50–66 s each. Both are in `out/`.

"Identical, test for test" is a set comparison of every non-passing `module::name`, not a
comparison of totals — four numbers can agree while naming different tests.

**Before the fix, the same instrument disagreed**, which is what makes the table above
evidence rather than decoration:

| seed | passed | failed | errors | extra failures vs file order |
|---|---:|---:|---:|---|
| `20260813` (pre-fix) | 447 | **13** | 63 | 6 × `test_row_factory_contract` `ScenarioNotSeeded` |
| `7` (pre-fix) | 447 | **13** | 63 | 6 × `test_row_factory_contract` `ScenarioNotSeeded` |

**The seeds really interleaved.** In all five, every one of the fourteen modules has at
least one test scheduled after the first `w4_database` arming — so every module has now
been exercised with `MAINLINE_DEMO_*` pointing at the proof world, and none changed
outcome. In three of five, a `test_row_factory_contract` test is scheduled directly
between two `w4`-consuming tests: the exact shape of §1.3.

```
w5-seed-1729.args      first w4-arming at #  4   first w1 at # 33   modules after arming 14/14   w1-between-w4 sandwiches 1
w5-seed-20260813.args  first w4-arming at # 12   first w1 at # 24   modules after arming 14/14   w1-between-w4 sandwiches 1
w5-seed-41.args        first w4-arming at #  2   first w1 at #229   modules after arming 14/14   w1-between-w4 sandwiches 2
w5-seed-7.args         first w4-arming at #  5   first w1 at # 36   modules after arming 14/14   w1-between-w4 sandwiches 0
w5-seed-99991.args     first w4-arming at #  7   first w1 at #  8   modules after arming 14/14   w1-between-w4 sandwiches 0
```

---

## 3 · Per-module isolation — all fourteen, alone

One pytest **process** per module, not one session: `db._conn`, `db._dsn_cache` and the
four `MAINLINE_DEMO_*` names are process state, so a second session in one interpreter
would inherit the thing being controlled for.

| module | tests | alone | in suite | agree | alone, seconds |
|---|---:|---|---|---|---:|
| `test_credentials` | 17 | 17P | 17P | yes | 1.4 |
| `test_demo_guard_anonymous` | 13 | 13P | 13P | yes | 0.3 |
| `test_envelope` | 50 | 50P | 50P | yes | 10.8 |
| `test_gate_run` | 28 | 27P 1s | 27P 1s | yes | 7.9 |
| `test_logbudget` | 39 | 39P | 39P | yes | 0.6 |
| `test_ratelimit` | 73 | 73P | 73P | yes | 0.5 |
| `test_reads` | 75 | 11P 1F 63E | 11P 1F 63E | yes | 2.9 |
| `test_refusal_row_factory` | 14 | 14P | 14P | yes | 2.8 |
| `test_response_contract` | 49 | 44P 5F | 44P 5F | yes | 0.4 |
| `test_routes_gate_run` | 11 | 11P | 11P | yes | 0.1 |
| `test_row_factory_contract` | 15 | 15P | 15P | yes | 6.7 |
| `test_seed_covers_every_console_resource` | 14 | 13P 1F | 13P 1F | yes | 1.0 |
| `test_static_site` | 93 | 93P | 93P | yes | 2.1 |
| `test_transitions` | 33 | 33P | 33P | yes | 11.6 |
| **total** | **524** | | | **0 disagreements** | 49.1 |

```
$ py scripts/qa/demo_suite_order.py diff --tag final --suite out/order/final-control.xml
   (no output, exit 0 — no CONTAMINATION, no HIDDEN-DEPENDENCE, nothing missing either side)
```

**The diff is falsified, not merely empty.** Pointed at a pre-fix seeded run it reports the
six contaminated cases by name:

```
$ py scripts/qa/demo_suite_order.py diff --tag w5 --suite out/order/pre-seed-7.xml
CONTAMINATION      test_row_factory_contract::test_resolve_through_the_production_connection
                     alone=passed in-suite=failed
                     ScenarioNotSeeded: no mainline.permit with permit_id 199adc10-…
   … five more …
```

The wave brief says thirteen modules; there are **fourteen** — W6 added
`test_seed_covers_every_console_resource.py` during this wave.

---

## 4 · The one skip, and its reason

There is exactly one skip in the whole suite, in the file this worker owns.

```
tests/test_gate_run.py::test_payload_validates_against_the_json_schema
  SKIPPED — "jsonschema is not a workspace dependency; the structural check above is
             what runs today and this turns green the day it is added"
```

Judged, not accepted:

| the claim | how it was checked | verdict |
|---|---|---|
| `jsonschema` is not importable | `python -c "import jsonschema"` → `ModuleNotFoundError` | true |
| it is not a dependency | `grep 'name = "jsonschema"' uv.lock` → no match; no `pyproject.toml` declares it | true |
| the assertion is not lost | `test_payload_satisfies_the_governing_contract_structurally` (line 875) runs and asserts the contract's required members, closed enums, and the `failures == [] ⟺ verdict == PROVEN` invariant against the same payload | true |
| it is a skip and not a deletion | `pytest.importorskip(..., reason=...)` — it turns green the day the dependency lands, with no edit | true |

> **Verdict: a real environmental fact, with a named reason and a hand-written floor
> underneath it.** It is not a failing test moved to skipped, and it is not a deleted test
> wearing a skip. Nothing to do.

---

## 5 · What it costs, and why

### 5.1 · The finding that dominates every other number here

`TRAPPOINT_DSN` as written in §4 of the wave plan spells the node `localhost`. Measured:

```
$ socket.getaddrinfo('localhost', 26257)   ->   ::1 FIRST, then 127.0.0.1
$ docker port trappoint-crdb               ->   26257/tcp -> 127.0.0.1:26257     (IPv4 only)
$ psycopg.connect('…@[::1]:26257…', connect_timeout=3)   ->   ConnectionTimeout after 3.07 s
$ psycopg.connect('…@localhost:26257…')    ->   10.080 s, 10.107 s
$ psycopg.connect('…@127.0.0.1:26257…')    ->    0.003 s,  0.002 s
```

The container publishes IPv4 only; `::1` **black-holes** rather than refusing, so libpq
waits out the whole `connect_timeout` (`db.CONNECT_TIMEOUT_SECONDS = 10`) on every
connection before falling back. The repository's own `DEFAULT_DSN` constants
(`test_gate_run.py:142`, `test_row_factory_contract.py:104`) already say `127.0.0.1`; the
10 s is imported entirely by the environment variable.

| whole suite, same tree, same order | wall clock |
|---|---:|
| `TRAPPOINT_DSN=…@localhost:26257…` | **1 557.96 s** (25 m 58 s) |
| `TRAPPOINT_DSN=…@127.0.0.1:26257…` | **66.39 s** |

A **23×** difference with no product change. The two runs differ in exactly three outcomes,
and all three are explained:

| test | `localhost` | `127.0.0.1` |
|---|---|---|
| `test_reads::test_health_is_200_with_a_real_schema_fingerprint` | **failed**, `assert 10.0464 < 5.0` | passed |
| `test_demo_guard_anonymous::test_the_four_refusals_leave_…_unchanged` | failed (`permit_rows_total 827 → 834`) | passed |
| `test_transitions::test_merging_an_already_merged_permit_…` | error, `SerializationFailure` | passed |

**This is not a licence to change the DSN in order to obtain a green.** It is the opposite:
it says W2's `/v1/health` failure is *not* a `health.py` defect. The endpoint does one round
trip; the round trip costs 10.04 s because opening the socket costs 10.04 s. The 5.0 s
ceiling stays exactly where it is, and the honest fix is to the address the lane dials, not
to the assertion. Two of the three are also latency-adjacent rather than order-adjacent, so
the CI lane's choice of spelling changes which failures it sees.

### 5.2 · Where the 1 557 s went — reproduced after the wave

`localhost`, file order, `out/demo-suite-w5-before.xml`, 502 tests:

| module | tests | seconds | s/test |
|---|---:|---:|---:|
| `test_transitions` | 33 | 554.1 | 16.79 |
| `test_demo_guard_anonymous` | 13 | 251.4 | 19.34 |
| `test_row_factory_contract` | 15 | 197.8 | 13.19 |
| `test_gate_run` | 28 | 194.7 | 6.95 |
| `test_reads` | 74 | 148.8 | 2.01 |
| `test_refusal_row_factory` | 14 | 139.0 | 9.93 |
| `test_credentials` | 17 | 57.0 | 3.35 |
| `test_envelope` | 50 | 10.8 | 0.22 |
| `test_static_site` | 93 | 2.1 | 0.02 |
| `test_logbudget` | 39 | 0.6 | 0.01 |
| `test_ratelimit` | 73 | 0.5 | 0.01 |
| `test_response_contract` | 42 | 0.3 | 0.01 |
| `test_routes_gate_run` | 11 | 0.0 | 0.00 |
| **total** | **502** | **1 557.0** | |

Slowest ten:

```
 50.43s  test_row_factory_contract::test_the_production_connection_really_is_dict_row
 50.21s  test_demo_guard_anonymous::test_the_four_refusals_leave_the_subject_and_every_row_count_unchanged
 41.10s  test_gate_run::test_gate_run_verdict_is_proven
 40.27s  test_demo_guard_anonymous::test_the_production_connection_is_the_one_db_py_opens
 40.25s  test_demo_guard_anonymous::test_the_four_posts_are_refused_with_the_permit_id_variable_unset
 40.24s  test_transitions::test_unknown_resource_is_404_and_not_an_envelope
 30.80s  test_transitions::test_every_outcome_hands_the_connection_back
 30.21s  test_gate_run::test_an_expired_receipt_is_repaired_by_issuing_one_not_by_editing_one
 27.34s  test_reads::test_health_reads_the_deploy_chain_marker_when_the_database_has_one
 22.32s  test_gate_run::test_concurrent_runs_do_not_collide
```

Every one of these is a multiple of 10.0 s to within a few hundredths, and the multiple is
the number of connections the test opens. **None of them is a slow test.** The lead's
reading — "session fixture setup billed to whichever test touched it first" — is not what
the numbers say: `test_the_production_connection_really_is_dict_row` is 50.4 s because its
fixture chain opens five sockets, not because it builds a database (the database was
adopted; a build costs ~50 s **more**).

### 5.3 · What the suite actually costs

`127.0.0.1`, file order, post-fix, `out/order/w5-control-default-order-after.xml`,
524 tests:

| module | tests | seconds | s/test |
|---|---:|---:|---:|
| `test_gate_run` | 28 | 14.9 | 0.53 |
| `test_envelope` | 50 | 11.3 | 0.23 |
| `test_transitions` | 33 | 10.8 | 0.33 |
| `test_row_factory_contract` | 15 | 9.3 | 0.62 |
| `test_refusal_row_factory` | 14 | 5.9 | 0.42 |
| `test_reads` | 75 | 4.0 | 0.05 |
| `test_credentials` | 17 | 2.6 | 0.15 |
| `test_static_site` | 93 | 2.2 | 0.02 |
| `test_seed_covers_every_console_resource` | 14 | 1.0 | 0.07 |
| `test_logbudget` | 39 | 0.9 | 0.02 |
| `test_response_contract` | 49 | 0.7 | 0.01 |
| `test_demo_guard_anonymous` | 13 | 0.5 | 0.04 |
| `test_ratelimit` | 73 | 0.5 | 0.01 |
| `test_routes_gate_run` | 11 | 0.0 | 0.00 |
| **total** | **524** | **64.7** | |

The single slowest case in this configuration is **10.08 s** —
`test_envelope::test_health_is_503_when_the_database_does_not_answer`, **15 % of the whole
suite in one test**. It dials `…@127.0.0.1:1/none?…&connect_timeout=2`, intending a two
second wait, and waits ten: `db._open` passes `connect_timeout=CONNECT_TIMEOUT_SECONDS`
(10) as a keyword, and psycopg's keyword beats the DSN's query parameter. The assertion is
about the 503 `reason` and is unaffected, so this is 8 s of waste rather than a wrong
answer — but it also means **a DSN's own `connect_timeout` cannot be honoured by this
module**, which is a fact about `db.py` worth knowing before a Cloud incident.

### 5.4 · A budget the CI lane can use

For the cluster-backed CI job, on a runner with a working IPv4 loopback and the databases
already built:

| line item | measured by W5 | note |
|---|---:|---|
| whole suite, warm fixtures, `127.0.0.1` | **48–66 s** | 524 tests, seven runs |
| whole suite, warm fixtures, `localhost` on an IPv6-first host | **1 558 s** | same tests, same tree |
| whole suite, `127.0.0.1`, **two scratch databases built from scratch** | **176 s** | first run of the A/B against `w_w5_order_w1` + `w_w5_order_w4`, both absent |
| whole suite, `127.0.0.1`, `w3_demo_api_<fp>` rebuilt after a seed edit | **169 s** | one chain + both seed files |

So a **cold** chain costs roughly **110 s per pair of scratch databases** on this node —
consistent with, and measured independently of, the lead's ~47 s per chain
(`docs/leads/demo-suite-plan.md` §0.3). The suite builds **four** databases in total:
`w3_demo_api_<fp>` (conftest), `w_w1_rowfactory`, `w_w4_api_transitions`, and
`w1_credentials_<fp>` (`test_credentials.py:162`).

**A budget:** a fully cold IPv4 run is **≈ 66 s of tests + ≈ 200 s of chains ≈ 4½ minutes**.
A **10-minute** timeout carries a twofold margin. A timeout that also has to survive a
runner where `localhost` resolves IPv6-first needs **35 minutes** — which is the argument
for the lane pinning the literal `127.0.0.1` (or the equivalent DNS-order flag) rather than
inheriting whatever `localhost` means on the runner it lands on.

---

## 6 · Every dependency found

| # | dependency | mechanism | status |
|---|---|---|---|
| 1 | `w1_database` ↔ `w4_database` fight over `MAINLINE_DEMO_{PERMIT_ID,SITE_ID,SIGNER_SUB,COUNTERSIGNER_SUB}` | two session-scoped fixtures, two databases, one process environment; last writer owns it for the session | **FIXED** in `test_row_factory_contract.py` — build stays session-scoped, publication is per-test |
| 2 | `w4_database` still publishes those four names for the whole session | `test_gate_run.py:450`; cannot be scoped down without breaking `run_once` (session-scoped consumer) and two modules W5 does not own that `from test_gate_run import w4_database` | **REPORTED, latent** — see §7 |
| 3 | an imported fixture is a **new `FixtureDef` per importing module** | `w4_database`'s body runs three times per session (measured); each run re-publishes the environment, which is what made #1 look intermittent | **REPORTED** — documented here so the next reader does not rediscover it as folklore |
| 4 | `w_w4_api_transitions` grows monotonically across runs | 834 `mainline.permit` rows measured, `PTW-W4-<hex>` family; nothing truncates it | **REPORTED** — cross-run, not cross-test; belongs to W4 |
| 5 | `db._conn` / `db._dsn_cache` / `db._dsn_source` module globals | `conftest.py::conn` calls `reset_dsn_cache()` before **and** after each test; `test_envelope.py`'s ten call sites each reset on the way out; `shared_conn`, `production_conn`, `anonymous_conn` and `_demo_gate_run_connection` each `db.close()` in a `finally`; no session-scoped fixture holds a connection object | **CHECKED, CLEAN** — no test flipped in five seeds |
| 6 | `logbudget` / `ratelimit` module-scope state | `test_logbudget.py:51`, `test_ratelimit.py:57` and `test_response_contract.py:133` each `reset()` **and** `configure()` before and after every test; `logbudget` has no `configure()` to restore (`reset()` is the whole restore) and `install()` is idempotent | **CHECKED, CLEAN** |
| 7 | `test_envelope.py`'s ten `reset_dsn_cache()` calls | each is paired with a `monkeypatch` env change that pytest undoes; the trailing reset is skipped only on a path that has already failed | **CHECKED, CLEAN** |
| 8 | the 63 `test_reads` errors are **not** an ordering defect | identical alone (63E) and in suite (63E) and in all five seeds; one session-scoped `payloads` fixture, `KeyError: 'commit_v2'` | **REPORTED** — belongs to W1/W2 |
| 9 | **cross-PROCESS**: two pytest sessions racing on `w3_demo_api_<fp>` | `demo_database` `DROP DATABASE … CASCADE` / `CREATE` / re-seed whenever the `w3_fixture.ready` marker is absent. Two concurrent sessions at the same fingerprint can each drop the other's freshly seeded database; the loser sees `_sole` refuse with `the seeded database holds 0 such rows where exactly one is required`. Observed as a 63 → 104 error swing with no file change | **REPORTED** — an advisory lock, or a per-session database suffix, would close it. Not W5's file |

---

### 6.1 · The census that says the list above is complete for the environment channel

The process environment is the channel the whole §1 defect travelled down, so it was
enumerated rather than sampled:

```
$ grep -rn 'os\.environ\[…\] *=|os\.environ\.(pop|update|setdefault)|putenv'  src/mainline_demo_api/*.py
   (nothing — no module under test writes the environment)

$ …same, over tests/*.py
   tests/test_gate_run.py               6 sites   (w4_database, _published_environment)
   tests/test_row_factory_contract.py   6 sites   (w1_database — now function-scoped)
   … and no other test module, at all.
```

**Every other module changes the environment only through `monkeypatch`,** which pytest
undoes at test teardown by construction — 50 uses in `test_response_contract.py`, 24 in
`test_static_site.py` and `test_envelope.py`, 22 in `test_logbudget.py`, 21 in
`test_ratelimit.py`, down to 0 in `test_credentials.py` (which passes an explicit mapping to
`scenario.from_env(...)` instead of touching the process at all — the most robust pattern in
the suite, and worth copying).

So the environment channel has exactly **two** raw writers, both in files W5 owns, both now
accounted for: one fixed, one recorded in §7(a).

---

## 7 · What is still there, and why W5 did not touch it

**(a) `w4_database` still publishes four environment variables session-wide.** It is the
mirror image of the defect fixed in §1.5 and it should have the same shape. It was left
alone deliberately, and this is the reasoning rather than an excuse:

* `run_once` (`test_gate_run.py:633`) is **session-scoped and requests `w4_database`**.
  Making `w4_database` function-scoped raises `ScopeMismatch` unless `run_once` is
  rewritten too.
* `test_demo_guard_anonymous.py` and `test_transitions.py` — **W4's files, not W5's** — do
  `from test_gate_run import w4_database`. A function-scoped fixture whose dependency lives
  in `test_gate_run.py` cannot be resolved from their fixture closures, so the split would
  have to be a memoised module function and both files would need re-reading.
* Several of W4's tests request `monkeypatch` alongside a `w4` fixture and delete these very
  names. Fixture finalisation is reverse-of-setup, so the restore order between
  `monkeypatch`'s undo and a function-scoped `w4_database`'s `finally` depends on argument
  order in files W5 may not edit — and getting it wrong re-creates the leak in a new place.

With #1 fixed, `w4_database` is now the **only** session-scoped writer of those names, so
there is nothing left for it to collide with, and five seeds × 524 tests confirm it: every
module runs after its arming in every seed, and nothing changed. It becomes a live defect
again the day a **third** scratch database is added. The fix, when W4 or the lead wants it,
is the one in §1.5 applied to `test_gate_run.py`.

**(b) Five failures in `test_response_contract.py` that were not there in the lead's
baseline.** A concurrent wave lowered `static_site.DEFAULT_MAX_RESPONSE_BYTES` from
`512 * 1024` to `136 * 1024` and rewrote `static_site.py` (+535 lines) and
`test_static_site.py`, without updating `test_response_contract.py`. The most serious of
the five is not a stale constant:

```
test_the_default_ceiling_refuses_the_declared_object_and_serves_the_declared_asset
  AssertionError: the ceiling refuses the console's own entry bundle   assert 413 == 200
test_the_declared_numbers_straddle_the_ceiling_rather_than_sitting_under_it
  assert 433396 < 139264
```

The console's entry bundle is **433 396 B identity / 124 127 B gzip**. Under the new
ceiling a client that asks for `identity` gets **413 for the demo's main bundle**. W5 did
not touch either side: the numbers are the authority here and both files are mid-flight
under another worker. These failures are **order-independent** — identical alone, in file
order and in all five seeds — so they are not this worker's defect class. Handed to the
lead.

**(c) The 63 `test_reads` errors** — `KeyError: 'commit_v2' is not an identifier the
deployed demo seed produces`, raised by the session-scoped `payloads` fixture
(`test_reads.py:95`). W1's `cr_id` work landed and the fixture's very next key is now
missing. Order-independent. Belongs to W1/W2.

**(d) For the lead, about how this wave measures itself.** Six workers sharing one node and
one working tree makes a whole-suite total a statement about the minute it was taken.
Concretely, and all measured tonight:

* `demo_world.sql` was rewritten at `00:18` and again at `00:32`; each rewrite changes
  `_fingerprint()`, renames `w3_demo_api_<fp>`, and forces a 271-file rebuild for the next
  session to start.
* Two sessions at the same fingerprint can each `DROP DATABASE … CASCADE` the other's
  freshly seeded fixture. The loser's `_sole` reports *"the seeded database holds 0 such
  rows where exactly one is required"* — which reads exactly like a seed defect and is not
  one. That is how a run went from 63 errors to 104 with no file change.
* Ten `python.exe` processes were live at `00:21`.

Two cheap countermeasures, neither of them W5's file: have `demo_database` take a
`pg_advisory_lock`-equivalent (CockroachDB: a marker row inserted with
`INSERT … ON CONFLICT DO NOTHING`) around the drop/create, and have every worker set
`MAINLINE_W1_DATABASE` / `MAINLINE_W4_DATABASE` to private names — those two overrides
already exist and are what this worker used for the batteries in §1.6 and §2. Until then,
**a merge decision made on one worker's four totals is a decision made on a coin flip**;
insist on a within-run comparison, which is what §1.6 is.

---

## 8 · The whole suite, before and after, under the lead's exact command

`--crdb=reuse`, `TRAPPOINT_DSN=…@localhost:…`, shared scratch databases, `--timeout=180`,
numbers from the XML root.

| | tests | passed | failed | skipped | errors | seconds |
|---|---:|---:|---:|---:|---:|---:|
| lead's baseline, `073dfea` | 444 | 375 | 5 | 1 | 63 | 1 535.9 |
| **W5 before** (`out/demo-suite-w5-before.xml`) | 502 | 429 | 8 | 1 | 64 | **1 558.0** |
| **W5 after** (`out/demo-suite-w5-after.xml`) | 524 | 452 | 8 | 1 | 63 | **1 679.0** |

The population grew by 22 between the two runs — other workers landed tests while these ran
— so the totals are not a like-for-like comparison and the per-test diff is:

```
tests present in BOTH runs whose outcome CHANGED:  2, both IMPROVED
  test_demo_guard_anonymous::test_the_four_refusals_leave_…_unchanged   failed  -> passed
  test_transitions::test_merging_an_already_merged_permit_…_epoch_pin   error   -> passed
tests that regressed:  0
tests removed:         0
tests added:          22   (all of them passing except the one below)
```

**Nothing regressed.** The two improvements are not claimed as W5's work: both are among the
three outcomes §5.1 shows to be sensitive to the loopback spelling and to cluster
contention, and neither is in a file W5 touched.

The eight failures and 63 errors in the "after" column are, in full:

```
63 E  test_reads (every case)     KeyError: 'commit_v2' …          W1/W2  (§7c)
 1 F  test_reads                  test_an_undeclared_query_parameter_is_refused…   W2
 1 F  test_reads                  test_health_is_200_with_a_real_schema_fingerprint  W2 (§5.1)
 5 F  test_response_contract      the 512 KiB / 136 KiB ceiling    cost wave (§7b)
 1 F  test_seed_covers_every_console_resource[silence]              W6
 1 s  test_gate_run               jsonschema importorskip          environment (§4)
```

None of them is order-dependent: each is identical alone, in file order and in every seed.

---

## 9 · Reproducing all of it

```powershell
$env:TRAPPOINT_DSN = "postgresql://root@127.0.0.1:26257/defaultdb?sslmode=disable"

# five seeded orders; prints the seed and the args file, and again on failure
py scripts/qa/demo_suite_order.py shuffle --seed 20260813 --seed 7 --seed 41 --seed 1729 --seed 99991

# each module alone, one process each
py scripts/qa/demo_suite_order.py modules

# contamination / hidden-dependence diff against a whole-suite XML
py scripts/qa/demo_suite_order.py diff --suite out/order/w5-control-default-order-after.xml

# the cost table off any JUnit XML
py scripts/qa/demo_suite_order.py timings out/demo-suite-w5-after.xml
```

Artefacts:

| what | where |
|---|---|
| final battery — control, five seeds, fourteen modules | `out/order/final-{control,seed-*,alone-*}.{xml,log}`, `out/order/final-battery.log` |
| the seeded orders themselves, replayable forever | `out/order/w5-seed-*.args` |
| the three-node-id reproducer | `out/order/probe-interleave.args` |
| the A/B against `HEAD`'s file | `out/order/ab-{before,after}-*.{xml,log}` |
| pre-fix seeded runs (13 failures each) | `out/order/pre-seed-{7,20260813}.xml` |
| the planted-defect run | `out/order/w5-planted-seed-7.xml` |
| whole suite, lead's command | `out/demo-suite-w5-{before,after}.xml`, `out/w5-{before,after}.log` |
| isolation diff, machine-readable | `out/order/final-isolation-diff.json` |
