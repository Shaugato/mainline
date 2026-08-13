<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# The CI skip census: what the hermetic lane does not execute

**Worker:** W1, CI-runs-the-cluster wave. **Measured 2026-08-13 on TRAPPOINT**, against the
working tree at `D:/CoackroachDBxAWS/mainline` (HEAD `073dfea` plus this wave's uncommitted
work) with `.venv/Scripts/python.exe` — Python 3.13.14, pytest 9.1.1, `win32`. Every number
below is the output of a command printed beside it, run in the same sitting as this file.
Nothing is carried forward from a recorded board.

The machine-readable form of everything here is
[`qa/ci-skip-census.json`](../../qa/ci-skip-census.json), written by
[`scripts/qa/ci_skip_census.py`](../../scripts/qa/ci_skip_census.py). This document is the
census in prose; the JSON is the census.

---

## 0. The one-sentence finding

> **988 of the 9839 tests this repository collects do not execute in CI. 974 of those 988
> are waiting on a database. 187 of them are the demo API — the product's headline path —
> and until this wave, no lane in this repository had ever pointed a cluster at that
> directory.**

Nothing on any dashboard distinguishes those 988 from a pass. The 187 were measured before
W2's `cluster-tests.yml` could run anywhere; §3 says exactly where that stands.

---

## 1. Why the question needs its own program

There is already a per-package census, `scripts/qa/report_test_state.py`, and it cannot
answer this question. It runs each target in its own subprocess, with its own selector, over
a target list it discovers by walking directories. That is the right shape for *"what does
each distribution do"* and the wrong shape for *"what does the CI lane skip"*, because the
answer to the second question is a property of one particular argv — the marker selector, the
`testpaths` in force, and the whole-repository collection those two produce together.

So the census runs the lane. Measured, the lane is one job:

```
$ grep -n 'all-packages pytest --crdb=none' .github/workflows/ci.yml
471:        run: uv run --frozen --all-packages pytest --crdb=none --collect-only -q
487:          uv run --frozen --all-packages pytest --crdb=none \
522:          uv run --frozen --all-packages pytest --crdb=none \
634:          uv run --frozen --all-packages pytest --crdb=none \
```

and the one at line 522 — `hermetic-tests`, step *"The suite, with every cluster test
SKIPPED FOR A NAMED REASON"* — is the only lane in this repository that runs the
whole-repository `testpaths` collection. It runs it with no cluster:

```
uv run --frozen --all-packages pytest --crdb=none -m "not (g4alpha or pl2_red)" -q --durations=10
```

`ci_skip_census.py` reads `RED_SELECTOR` out of `ci.yml` as raw text rather than restating
it, so the census follows the lane when the red-by-design set changes instead of quietly
measuring last month's selection.

### The idea was already in the file, twice, and neither copy counted anything

`ci.yml:565-575` lists three guards against a vacuous pass, and the third is this one by
name:

```
#   * a SKIP CENSUS — `--crdb=none` cannot measure a cluster-backed test, and a test
#     that was not measured is not evidence of anything, so skips are counted, named
#     and never allowed to satisfy the floor.
```

That guard is real and it works — over the **fifteen** tests the `red-by-design` job
selects. The other **9824** are collected by the job next door, whose own step comment
(`ci.yml:508-513`) makes the claim in the strongest possible terms:

```
# `--crdb=none` makes the fixture skip and PRINT the reason it skipped, so `-ra`
# renders a census of exactly what this lane did not prove. That census is the honest
# half of a green tick.
```

It renders it to a **log**. Nothing counts it, nothing names it against a lane, nothing
refuses an increase, and the log expires. This file is that sentence taken at its word for
the rest of the collection: the same census, as a committed artefact with a `--check`.

### What the census adds to that argv, and why none of it changes a verdict

| added | why |
|---|---|
| `--junit-xml <tmp>` | the skip reason arrives as a `<skipped message=…>` attribute — one element per test — instead of a line to be regexed back out of a terminal report that groups identical reasons under one `SKIPPED [n]` heading and re-wraps them for a human |
| `-o junit_family=xunit1` | measured on pytest 9.1.1, the default `xunit2` emits only `classname`, `name` and `time`. A skip that cannot name its file cannot be attributed to a test root or to a lane. `ci.yml`'s `red-by-design` job already sets this, for the same reason and in the same words |
| `-p no:cacheprovider` | the census must not leave a `.pytest_cache` behind in a tree five other workers are writing to |
| `python -m pytest` instead of `uv run --frozen --all-packages` | `uv --version` is `command not found` on this machine; the interpreter is the pinned `.venv` one that resolves the same lockfile, and `tool.python_executable_is_venv` in the JSON records that it was |

The four spellings of the DSN (`MAINLINE_TEST_DSN`, `COCKROACH_URL`, `CRDB_URL`,
`TRAPPOINT_DSN`) are **removed** from the subprocess environment. CI has none of them set,
and a census taken with a DSN in the environment would be measuring a different lane than the
one it names.

---

## 2. The measurement

```
$ .venv/Scripts/python.exe scripts/qa/ci_skip_census.py
lane: .github/workflows/ci.yml · job hermetic-tests · selector 'g4alpha or pl2_red'
wrote D:\CoackroachDBxAWS\mainline\qa\ci-skip-census.json
9839 collected · 8829 passed · 6 failed · 1 errored · 988 skipped · 15 deselected
974 of 988 skips are cluster-shaped; 14 are not; 46 distinct reason strings
```

512.3 s of wall clock. pytest exit `1`. `qa/ci-skip-census.json` is 567 KB, because it
carries one entry per skipped test rather than one per reason string — which is the whole
point: a rollup by reason cannot be attributed to a workflow.

| | count |
|---|---:|
| collected | **9839** |
| passed | 8829 |
| failed | 6 |
| errored | 1 |
| **skipped** | **988** |
| deselected (the red-by-design set, run by `red-by-design`) | 15 |

`8829 + 6 + 1 + 988 = 9824`, plus `15` deselected = `9839`. `collected` is the only number
here that is not read out of the JUnit report: JUnit has one `<testcase>` per test that was
*selected*, and has no element at all for a deselected one, so the deselection count comes
from pytest's own terminal summary and is labelled `deselected_source` in the JSON.

**A deselected test is not a skipped test.** The 15 are the `g4alpha` / `pl2_red` cases, and
`ci.yml`'s `red-by-design` job executes exactly them and inverts the verdict. They are
reported separately here and are never folded into `skipped`.

---

## 3. Where the 988 are

Per test root, every root that skips anything:

| test root | collected | passed | skipped | of those, cluster-shaped |
|---|---:|---:|---:|---:|
| `tests/integration` | 1812 | 1270 | 542 | 539 |
| `packages/trappoint-conformance` | 220 | 33 | 187 | 187 |
| `verticals/mainline/apps/demo-api` | 445 | 258 | **187** | **187** |
| `packages/trappoint-diagnose` | 143 | 126 | 17 | 17 |
| `tests/concurrency` | 36 | 20 | 16 | 15 |
| `tests/release` | 190 | 169 | 15 | 15 |
| `packages/trappoint-model` | 33 | 22 | 11 | 11 |
| `tests/boundary` | 127 | 121 | 6 | 0 |
| `tests/unit` | 3529 | 3525 | 3 | 1 |
| `packages/trappoint-testkit` | 28 | 26 | 2 | 2 |
| `tests/security` | 467 | 465 | 2 | 0 |

Seventeen further roots skip nothing at all: `packages/mainline-agentkit`,
`packages/mainline-boundary`, `packages/mainline-mcp`, `packages/trappoint-core`,
`packages/trappoint-jcs`, `packages/trappoint-ledger`, `packages/trappoint-migrate`,
`packages/trappoint-sql`, `packages/trappoint-verify`, `tests/agents`, `tests/deploy`,
`tests/e2e`, `tests/eval`, and all four of `verticals/mainline/packages/*`.

The three that matter to this wave, in one line each:

* **`verticals/mainline/apps/demo-api` — 187 of 445.** When this wave opened,
  `grep -rn "demo-api" .github/workflows/` returned nothing across all eighteen files, while
  nine of them stood up a CockroachDB container. **That changed during this sitting**: W2's
  `cluster-tests.yml` landed, the directory is now 19 files, and the grep returns twelve
  lines, all of them in that one new lane. The 187 above were measured before it could run
  anywhere, and the census is what its first green will be measured against.
* **`packages/trappoint-conformance` — 187 of 220.** `schema.yml` runs `unweld/` and four
  named files, not `tests/test_conformance_cases.py`, where most of these live. *(Stated here
  as a reading of the workflow file, not as a measurement — see §7.)*
* **`tests/integration` — 539.** `custody-chain.yml` runs `tests/integration/custody`. The
  rest of the tree, including `tests/integration/schema`, is named by no lane. *(Same caveat.)*

---

## 4. What "cluster-shaped" means, and the defect in the first version of it

The flag is a property of the **reason string the fixture wrote**, not of the test:

```
(?i)(--crdb=|crdb|cockroach|cluster|\bDSN\b|_DSN\b|\bdatabase\b|\bnode\b)
```

`974` of `988` match it; `14` do not; there are `46` distinct reason strings in total, and
the JSON publishes every one of them with the side it landed on, so a reader can disagree
with the classification without re-running anything.

**The first version of that expression was wrong, and the way it was wrong is worth
recording.** It read `\bcluster\b` and `\bcrdb\b`. `_` is a word character, so `\bcluster\b`
does not match inside `MAINLINE_MCP_CLUSTER_ID` or `CRDB_CLUSTER` — and 32 skips whose reason
string literally asks for a cluster id fell out of the count:

```
941 of 987 skips are cluster-shaped   <- \bcluster\b, first draft, run 1's data
974 of 988 skips are cluster-shaped   <- cluster, no boundary, run 2's data
```

(The `987` → `988` between those two lines is the tree moving, not the classifier — see §5.
Re-classified over run 1's own data, the boundary-free expression gives `973 of 987`, which
is the lead's number to the test.)

Over-inclusion is also the **safe** direction here, and that is the second reason the
boundaries came off. Under W4's ratchet, a cluster-shaped skip must be attributed to a named
lane or to an enumerated `unlanded` entry with a reason before the build is satisfied. A skip
wrongly marked cluster-shaped therefore costs someone a sentence. A skip wrongly marked
*not* cluster-shaped escapes attribution altogether and goes on reading as green — which is
the exact failure this wave exists to end.

### The 33 that a container cannot unskip

Of the 974 cluster-shaped skips, **33 do not want a node at all**. They want a CockroachDB
*Cloud* credential — a Managed-MCP API key and a cluster id, or an unattended `ccloud` login:

```
no Managed-MCP credential: set MAINLINE_MCP_API_KEY and MAINLINE_MCP_CLUSTER_ID
(or CC_API_KEY and CRDB_CLUSTER). …                                              ×30
no Managed-MCP credential: set CC_MCP_API_KEY and MAINLINE_MCP_CLUSTER_ID. …     ×2
unattended `ccloud` auth is undocumented (§9.3 …) and this build has no
CockroachDB Cloud organisation …                                                 ×1
```

All 33 are in `tests/integration`. W2's lane could stand up a pinned single node all day
without moving one of them. They are still cluster-shaped and they still have to be
attributed; they simply cannot be attributed to a lane that runs a container. They are
published as a named subset, `cluster_shaped.needs_a_credential_not_a_node`, precisely so
that a ratchet does not file them under a lane that can never execute them.

### The 14 that are not cluster-shaped, in full

| count | reason, verbatim (truncated for the page; unabridged in the JSON) |
|---:|---|
| 2 | neither `conftest` nor `opa` is on PATH, so the Rego re-statement of E1/E2/E4 was not evaluated… |
| 2 | refused before the pipeline runs; covered by test_layers.py |
| 1 | N=64 is the nightly arm: set TRAPPOINT_NIGHTLY=1… |
| 1 | insert_rows is a real append to a real evidentiary table; set MAINLINE_MCP_ALLOW_WRITE=1… |
| 1 | live IAM simulation not attempted: MAINLINE_BOUNDARY_LIVE_AWS is not set to 1… |
| 1 | live IAM simulation unavailable: MAINLINE_BOUNDARY_LIVE_AWS is not set to 1 |
| 1 | mainline-delta-oracle is installed in this environment; the AST checks still prove the lattice does not import it… |
| 1 | no kernel-image SBOM is committed at evidence/sbom/kernel/current.cdx.json… NOT A PASS |
| 1 | pyproject.toml does not declare 'trappoint-recall-verify-per'… |
| 1 | sentence-transformers is the 'local-embed' extra and the bge-large weights are a network fetch… |
| 1 | spec/agents/fleet.yaml does not exist yet (owned by the agent-contracts-red worker)… |
| 1 | the repository README makes no Proof-of-Exhausted-Recall claim yet, so it owes no bound… |

Twelve strings, fourteen tests. Every one of them says what did not happen and refuses to
call itself a pass. That is the house style working; none of these is a defect.

---

## 5. This census against the lead's, and against itself

The lead measured the same lane earlier the same day and recorded
`1 failed, 8835 passed, 987 skipped, 15 deselected` out of `9838`, with `973` cluster skips,
`14` others and `35` distinct reason strings. One of those agrees exactly and four differ,
and each difference has a cause:

| | lead | this census | why |
|---|---:|---:|---|
| collected | 9838 | 9839 | one demo-api test landed in between. It landed *between this census's own two runs* as well — see below |
| skipped | 987 | 988 | the same test, skipped for want of a cluster |
| cluster / other | 973 / 14 | 974 / 14 | agrees. Two independent classifiers, the same split |
| distinct reasons | 35 | 46 | the lead counted reason strings out of a `-ra` terminal report, which groups identical reasons under one `SKIPPED [n]` heading and re-wraps them; JUnit carries one `message` attribute per test, so strings the terminal report folded together are distinct here |
| failed | 1 | 4 | three failures landed in this wave and none is this worker's — see §7 |

**And this census disagreed with itself, twenty minutes apart.** Three runs of the same
lane on the same afternoon:

```
run 1, 610.2 s   9838 collected · 987 skipped · 1 failed · demo-api 186 cluster-shaped skips
run 2, 576.1 s   9839 collected · 988 skipped · 4 failed · demo-api 187 cluster-shaped skips
run 3, 512.3 s   9839 collected · 988 skipped · 6 failed · demo-api 187 cluster-shaped skips
```

A test file grew a test while the first run was executing; two more failures appeared
between the second and the third, and both of those are named in §7 and owned here. What
does **not** move across the three is the shape: 988 skipped, 974 cluster-shaped, 14 not,
the same eleven roots. That is not noise to be smoothed away — it is the property that
makes `--check` worth having. The census is a measurement of a tree at a moment, and the
moment is in the file.

---

## 6. Re-deriving it, and keeping it honest

```
$ python scripts/qa/ci_skip_census.py            # measure and write qa/ci-skip-census.json
$ python scripts/qa/ci_skip_census.py --check     # re-measure and refuse any drift
$ python scripts/qa/ci_skip_census.py --summary-only   # read the committed file, run nothing
```

`--check` re-runs the lane and diffs the fresh measurement against the committed file, naming
every difference: a count that moved, a root whose row changed, a skip that appeared, a skip
that stopped skipping, a reason string that was rewritten. Exit `1` on any of them.

Run back to back against the committed file, on a tree five workers were writing to:

```
$ python scripts/qa/ci_skip_census.py --check
9839 collected · 8829 passed · 6 failed · 1 errored · 988 skipped · 15 deselected
974 of 988 skips are cluster-shaped; 14 are not; 46 distinct reason strings

no drift against D:\CoackroachDBxAWS\mainline\qa\ci-skip-census.json
CHECK_EXIT=0
```

Two independent 8½-minute executions of the whole collection, and all 988 skip node ids,
all 28 root rows and all seven counts agree. `--check` is therefore a real gate and not a
coin toss — which had to be demonstrated rather than assumed, given that the same command
returned `9838 / 987` an hour earlier (§5).

The exit status is about the **census**, not about the suite:

| exit | means |
|---:|---|
| 0 | the lane ran and the census was written — **including when the suite is red**. Recording a failure is the job |
| 1 | `--check` found drift |
| 2 | the tooling is wrong: pytest could not be run, `ci.yml` no longer declares exactly one `RED_SELECTOR`, or a `--check` was asked for across a different pytest, Python minor or operating system |

That last row is deliberate. A census taken on `win32` and compared against one taken on
`ubuntu-24.04` would report differences it cannot attribute — a skip conditioned on a missing
binary or on `sys.platform` falls differently on the two — so the script refuses the
comparison and says why, rather than emitting a red nobody can act on. `qa/ruff-ratchet.json`
refuses to compare across ruff versions for the same reason.

---

## 7. What this file does **not** say

* **It does not say which lane runs which skipped test.** That column is W4's, and it cannot
  be derived by grepping paths out of workflow files. The lead tried: checking whether a
  skipped file's path or any prefix of it appears in a non-comment line of any workflow
  returned `968 covered / 19 uncovered`, which is nonsense — `demo-api/tests/conftest.py`
  came back "covered by eleven workflows" because the substring `verticals` occurs in eleven
  files. The only sound method is to lift each lane's exact pytest argv out of its workflow
  and run it with `--collect-only`, recording which node ids it reaches. The sentences in §3
  about `schema.yml` and `custody-chain.yml` are readings of those files, not measurements,
  and are marked as such.
* **It does not say the 988 are bad tests.** Almost every one of them refuses to pass rather
  than pretending. The defect is not in the tests; it is that no lane executes them and no
  page said so.
* **It does not measure `ubuntu-24.04`.** Every count is what this operating system and this
  interpreter observed. `tool` in the JSON records both.
* **It does not adjudicate the six failures and one error in the run.** It names them,
  because a census that reported `6 failed` and left it there would be the thing this file
  argues against. Measured this sitting, four failures and the error belong to files this
  worker does not own:
  `tests/release/test_check_reuse.py` (2 failed, 1 error),
  `tests/release/test_ruff_ratchet.py::test_the_ratchet_passes_on_the_real_tree` — which
  names a `[HARD GATE]` `ISC004` in `scripts/ci/cluster_lane_report.py` and 226 files the
  formatter would rewrite — and
  `tests/unit/domain/canon/test_idempotence.py::test_canon_is_idempotent`.
  **The remaining two are this worker's, on purpose**, and are the pair in §8.2:
  `test_honesty_is_checkable.py::test_every_quantity_equals_the_value_it_cites` and
  `::test_no_citation_is_decorative`. That file was `34 passed` before the demo-api rows
  landed in `qa/test-state.json` and is `2 failed, 32 passed` after. It is not collateral
  damage; it is the mechanism firing.

---

## 8. The sibling census, and the third occurrence of one defect

`qa/test-state.json` — the per-distribution census — carried **26 targets and no demo-api row
at all**. `scripts/qa/report_test_state.py` discovered its targets from

```
for pattern in ("packages/*", "verticals/*/packages/*"):
```

and `verticals/*/apps/*` was absent. So the file `docs/HONESTY.md` cites most often for test
state did not contain a single number about the 445 tests on the product's headline path.

**This is the third occurrence of one defect class, one directory level across:**

| date | declaration | what it missed |
|---|---|---|
| before 2026-08-10 | `testpaths = ["tests", "packages"]` | 146 tests in `verticals/*/packages/*` |
| before 2026-08-13 | `+ verticals/*/packages/*/tests` | 228 tests in `verticals/*/apps/*` |
| this file | `report_test_state.py`'s two glob patterns | 445 tests in `verticals/mainline/apps/demo-api` |

The fix names the app rather than globbing it, exactly as `pyproject.toml` already argues in
writing above its own `testpaths`: `verticals/mainline/apps/` holds three entries and only
one is Python. `console/tests` is a vitest suite — 148 entries, zero `*.py` — and handing it
to pytest is the same category error that `[tool.uv.workspace] members` refuses one file
over. `steward` has no `tests/` at all. So:

```
NAMED_APP_TARGETS: tuple[str, ...] = ("verticals/mainline/apps/demo-api",)
```

Adding an app there is a deliberate line, which is the point.

```
$ python scripts/qa/report_test_state.py --list-targets | grep demo-api
verticals/mainline/apps/demo-api	distribution	verticals/mainline/apps/demo-api/tests
```

The two rows were then measured and folded in through that file's existing `merges`
mechanism — `--targets verticals/mainline/apps/demo-api --merge` — and **not** by
regenerating the whole census, which takes 2414 s and would rewrite 26 rows this worker did
not measure while five other workers are writing to the tree.

```
verticals/mainline/apps/demo-api   --crdb=none    445 tests · 258 P ·   0 F ·  0 E · 187 S ·  16.2 s
verticals/mainline/apps/demo-api   --crdb=reuse   445 tests · 380 P ·   1 F · 63 E ·   1 S ·  45.7 s
```

### 8.1 The wedge that cost three attempts, and why the default was not changed

The first two attempts at the cluster row did not produce a row. They produced this, twice:

```
cluster · verticals/mainline/apps/demo-api … 0P 0F 0E 0S in 900.02s [TIMED OUT]
```

— while the identical suite, run by hand, finished in 43 s. The difference is one word.
`report_test_state.py` publishes its DSN under the four environment names, and its default
DSN says `localhost`. Measured on this machine, with the node published by
`-p 127.0.0.1:26257:26257`:

```
$ python -c "import socket; print(socket.getaddrinfo('localhost', 26257, type=socket.SOCK_STREAM))"
    AF_INET6  ('::1', 26257, 0, 0)          <- tried first
    AF_INET   ('127.0.0.1', 26257)

  127.0.0.1: CONNECTED in 0.00s
        ::1: TimeoutError after 6.00s        <- the SYN is dropped, never refused
  localhost: CONNECTED in 6.03s              <- socket.create_connection has a timeout
                                                and falls through to the IPv4 address
```

`socket.create_connection` carries a timeout, so it recovers after six seconds.
`psycopg.connect` given **no `connect_timeout`** does not — it sits in
`waiting.wait_conn` → `select.select` and never returns. The demo API's
`tests/test_credentials.py:200` connects exactly that way:

```
File ".../verticals/mainline/apps/demo-api/tests/test_credentials.py", line 200,
     in demo_world_dsn
  with psycopg.connect(dsn, autocommit=True) as conn:
File ".../psycopg/waiting.py", line 112, in wait_conn
  if not (rlist := sel.select(timeout=interval)):
+++++++++++++++++++++++++++++++++++ Timeout +++++++++++++++++++++++++++++++++++
```

`demo_world_dsn` is a session-scoped fixture, and `pyproject.toml`'s own comment above
`timeout_method = "thread"` already records that pytest-timeout cannot interrupt a hang
there. So the whole target wedges rather than failing — which is, word for word, the
failure mode `report_test_state.py`'s header was written about: *"fixtures connect with no
`connect_timeout`… the run did not fail — it WEDGED."*

**The default DSN was not changed to dodge it.** `localhost` is what this project's runbook
publishes, a GitHub runner resolving `localhost` to `::1` would hit the same wall, and
moving the instrument so it stops touching the defect is how a defect becomes permanent and
invisible. What changed instead is that every merge now records the host it actually
dialled, so a reader can tell which spelling produced the numbers:

```
* `2026-08-13T11:50:38Z` — `verticals/mainline/apps/demo-api`, `--crdb=reuse`,
  ceiling 900 s, dialled `127.0.0.1:26257`
```

The defect itself belongs to `test_credentials.py`, which this worker does not own and did
not touch. It is reported, not repaired.

### 8.2 A row that was true and not representative

The third attempt produced `433 P · 11 F · 0 E · 1 S` — no errors at all, where every
hand-run of the same suite that day reported `63 E`. It was not a measurement error: at that
minute another worker had `test_reads.py` in a state where the `payloads` fixture resolved
and ten of its assertions failed instead. `test_reads.py` was rewritten again eight minutes
later (mtime `21:41`), and the suite returned to `380 P · 1 F · 63 E · 1 S`.

A census row is a snapshot, so a snapshot of somebody's half-finished edit is *honest* and
*useless*. It was re-measured, and the committed row is the fourth attempt, which agrees
exactly with a hand-run taken minutes apart. The superseded attempts are still in the file's
`merges` list, with their timestamps, because that list is what makes a row datable.

> **Consequence, stated here because it is a real one and it is red right now.**
> `report_test_state.py` recomputes `totals` from every row present on every merge, on
> purpose — a stale total is the one number in that file a reader would not think to check.
> Adding the demo-api rows therefore moves the totals, and `docs/HONESTY.md` lines 357-365
> and 365 quote them by reference. `tests/release/test_honesty_is_checkable.py` enforces
> that the printed value equals the value at the reference, so it went from `34 passed` to
> `2 failed, 32 passed` the moment the rows landed:
>
> ```
> line 357  totals.none.targets      27   page prints 26
> line 358  totals.none.tests      9290   page prints 8845      totals.cluster.tests    7632  / 7187
> line 359  totals.none.passed     8323   page prints 8065      totals.cluster.passed   7340  / 6960
> line 360  totals.cluster.failed    30   page prints 29
> line 361  totals.cluster.errored  245   page prints 182
> line 362  totals.none.skipped     923   page prints 736       totals.cluster.skipped    17  / 16
> line 365  skip_reasons.none|len    44   page prints 43
> ```
>
> It is red for the right reason: a published number stopped matching its source the moment
> the source got truer. **The fix is to re-derive that page, not to move any number in
> `qa/test-state.json`.** Re-deriving it is W5's, and W5's brief already anticipates this in
> as many words — *"W1 will have added demo-api rows to that file, so re-derive, do not do
> arithmetic."*

---

## 9. The sentence this document exists for

`docs/ci/test-collection.md` recorded that the demo API's tests were not *collected*, and
that was fixed: `testpaths` reaches them and a default `pytest` now sees all 445.

**Collection is not execution.** They are collected, they are named in the census, and in CI
they still do not run.
