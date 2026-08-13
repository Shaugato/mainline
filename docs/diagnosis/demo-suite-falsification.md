<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# The demo-suite wave, falsified — every claimed fix put back by hand

**Worker:** `w6-falsification-audit` · **Measured 2026-08-13/14 on TRAPPOINT**, HEAD `073dfea`
**plus this wave's uncommitted working tree** · `.venv` pytest 9.1.1 / psycopg 3.3.4 · local
CockroachDB CCL **v26.2.5** on `127.0.0.1:26257` · scratch database `w_w6_falsification_audit`
(`MAINLINE_W4_DATABASE`) so no plant of mine writes into a database another run is measuring.

**The command is `scripts/qa/demo_suite_falsification.py`.** Everything below is its output
or the junit XML it wrote. Nothing here is a summary of somebody's claim; each row is an
experiment that was run.

---

## 0 · The result, in one table

| case | worker | verdict |
|---|---|---|
| `w1-change-request-absent` | `w1-change-request-seed` | **DEMONSTRATED** |
| `w2-read-surface-standing` | `w2-read-surface` | **DEFECT STANDING** — no fix landed |
| `w3-counter-that-decomposes` | `w3-raising-branch` | **DEMONSTRATED** |
| `w4-a-refusal-that-writes` | `w4-refusal-that-writes` | **DEMONSTRATED** |
| `w5-order-independence-reproduction` | `w5-order-independence` | **ORDER-DEPENDENCE CLOSED** — its own reproduction, see §4.3 |
| `w6-console-declares-a-thirteenth-resource` | `w6-falsification-audit` | **DEMONSTRATED** |

Whole-suite numbers, from the junit XML root elements, are in §7.

**Three things this audit found that no worker reported**, and they are the reason a
falsification pass is worth a worker rather than a paragraph:

1. **W1 did not reach the "0 errors" its brief required.** The `KeyError` moved rather than
   went: 63 setup errors that read `'cr_id' is not an identifier the deployed demo seed
   produces` now read **`'commit_v2'`**. §2.
2. **A seed plant is VACUOUS unless the fixture database is dropped first**, and it was
   vacuous the first two times I ran it. `w3_fixture.ready` certifies that a database was
   *built*; it does not certify *what it was built from*. §6.
3. **The demo seed's `silence` resource cannot be rendered at all.** The new console-coverage
   test found it on its first run against a cluster. §5.

---

## 1 · What a case is, and what "demonstrated" costs

Each case names the worker, the exact edit that puts the defect back, the pytest node ids to
drive, and the strings the red must contain. A case is **DEMONSTRATED** only when all four of
these hold:

1. the same nodes are run **without** the plant and are **green** — a test that was already
   failing proves nothing when it fails again;
2. the plant turns them **red** — not skipped, not errored on a fixture race;
3. every expected string appears in the failure text;
4. the message **names the right file**.

Anything else is `INCONCLUSIVE`, `NOT DEMONSTRATED`, `RED FOR THE WRONG REASON` or `RED BUT
UNATTRIBUTED`, and those are four different sentences on purpose.

**Reverting is proved by bytes, not by `git diff --exit-code`.** Every file a case touches is
read before the run and written back in a `finally`, and its SHA-256 is compared with what it
was. That is the binding proof, and it is stronger than the bare command the brief asks for,
because **this working tree is not clean to begin with**: five concurrent waves have
uncommitted work in it, so `git diff --exit-code` returns 1 before this program starts and
would return 1 however carefully it behaved. So the harness reports three things — the
per-file SHA-256 check, a `git diff` digest **scoped to the files it planted into**, and the
whole-tree digest for context. During one 13-minute run the whole-tree digest moved because
two neighbouring workers landed files into `verticals/mainline/apps/demo-api/tests/` while I
was working; the scoped digest did not move, and the per-file check passed on every case.

---

## 2 · W1 — the change request is load-bearing, and the errors did not go to zero

**The plant.** `verticals/mainline/db/seeds/demo/demo_world.sql` §10 is cut out — the
`change_request`, its `cr_clause`, its obligation and its genesis `cr_event` — which is the
state the seed was in at `073dfea`.

**The result: DEMONSTRATED.** Control green in 25.3 s; planted red naming `conftest.py` and
carrying every expected string:

```
failed on setup with "AssertionError: mainline.change_request — the demo's second gated
subject: the seeded database holds 0 such rows where exactly one is required. This database
was built by applying demo_world.sql, demo_permit.sql out of …/db/seeds/demo; if those files
no longer produce this row then the DEPLOYED demo no longer carries it either, and that is
the defect — not this assertion."
```

The row W1 added is what the fixture reads, the fixture reads it with a query, and removing
it is a red that names the seed file. **W1's seed change is not a value reshaped to match a
constant** — I checked that separately: every identifier in §10 is a fresh `dec0de00-…`
literal, and `grep` for `dec0de00-000c-4000-8000-000000000001` under
`verticals/mainline/apps/demo-api/src/` finds nothing.

**But W1's stated done-when is not met.** Its brief required *"`pytest … --crdb=reuse`
reports **0 errors**"*. Measured on the whole suite at the start of this audit:

```
out/demo-suite-w6-falsification-audit-before.xml
  tests=502 failures=8 errors=64 skipped=1 time=1558.182

63 × failed on setup with "KeyError: "'commit_v2' is not an identifier the deployed demo
                           seed produces. …"
```

`tests/test_reads.py:95` addresses `clause_version` at `seed["commit_v2"]`, and
`conftest._identifiers` produces `commit_id` — the commit the *check* cites — and no
`commit_v2`. So the session-scoped `payloads` fixture still raises on its **fifth** entry
instead of its **second**, and the same 63 tests still error. This is not a criticism of the
ruling in §1.1 of the plan, which was right; it is that the ruling was implemented one name
short. **Whoever owns the second commit — `conftest.py` is W1's file, `test_reads.py` is
W2's — has to close it, and until then the suite has 63 errors and reads as though it has
none if you only read the four-line summary.**

---

## 3 · W2 — nothing landed, and both defects are still there

Run as they stand, no plant:

```
verticals/mainline/apps/demo-api/tests/test_reads.py
    ::test_an_undeclared_query_parameter_is_refused_rather_than_ignored     FAILED
    ::test_health_is_200_with_a_real_schema_fingerprint                     FAILED
2 failed in 34.8s
```

* `assert [] == [0, 1]` — the ledger range read still returns no leaves.
* `assert 10.11 < 5.0` — `/v1/health` still takes ten seconds against a five-second ceiling.

Both reproduce the baseline exactly. `reads.py`, `health.py` and `app.py` carry no change
from this wave, and the 404 test for an unknown `cr_id` that W2 was to add does not exist:
`grep -c "cr_id" tests/test_reads.py` finds the fixture reference and no not-found case.
**There is no fix to falsify.** Recorded as a standing defect rather than as a gap in this
audit.

---

## 4 · W3, W4 and W5

### 4.1 · W3 — the raising branch: DEMONSTRATED

**The plant** puts `_RAISES` back to `gate_closed_when_issued` and `_RAISES_COUNTER` back to
`open_blocking` — the instrument the file used before W3 moved it. Control green (3 tests,
50.4 s); planted red on all three, naming `test_refusal_row_factory.py`:

```
AssertionError: mainline.permit.open_blocking is 1, not 0, on the seeded permit, so
trappoint.explain_refusal will now DECOMPOSE 'gate_closed_when_issued' instead of refusing
to (0119a:189). … do NOT weaken the assertions below, and do NOT reshape the seed to restore
this number.
```

That is the strongest form of this result: W3's **new** test
(`test_the_counter_behind_the_raising_constraint_is_zero`) is what goes red first, and it
names the counter, the constraint and the line of the migration. The drift that took two
tests down silently now arrives with its own diagnosis.

### 4.2 · W4 — a refusal that writes: DEMONSTRATED

**The plant** makes `transitions._demo_guard` commit an `INSERT INTO mainline.permit` on the
`demo_subject_unidentified` path and *then* return its 423 — the screen says no, the database
says yes. The `conn.rollback()` at the call site (`transitions.py:1236`) is why the plant
commits: a plant without the commit would be swallowed and would prove nothing.

Control green (75.1 s); planted red naming `test_demo_guard_anonymous.py`:

```
AssertionError: {'permit_rows_total': (1, 5),
 'permits_that_appeared': ["0b700cfc-… external_ref='FALSIFY-04…' opened_at=2026-08-13
   14:36:40.098996+00:00 minted by no fixture in this suite mints that external_ref —
   this is the API's own write"]}
assert {'state': 'di...king': 1, ...} == {'state': 'di...king': 1, ...}
  Differing items:
  {'permit_ids': frozenset({'0b700cfc-…', '0ef7b882-…', '0fcc7f86-…', '64b2972e-…',
                            'd1183212-…'})} != {'permit_ids': frozenset({'0ef7b882-…'})}
  {'permit_rows_total': 5} != {'permit_rows_total': 1}
```

(One row per POST: four appeared, and `permit_rows_total` went 1 → 5. The count and the set
agree here because the plant only inserts; the set is what makes the four rows *nameable*,
and it is what would still fire if the plant had also deleted one.)

**W4's change is exactly as strong as it claims.** The four POSTs are still refused — the
`refused ==` clause passes — and the row-set clause catches the write anyway, names the row,
names its `external_ref`, and says in as many words that no fixture in the suite minted it.
A count could not have said any of that. Four planted rows were deleted from
`w_w6_falsification_audit` afterwards by the harness.

### 4.3 · W5 — its own published reproduction, re-run

W5 published a three-node reproduction (`docs/ci/demo-suite-order.md` §1.3) of the
`w1_database` ↔ `w4_database` fight over the four `MAINLINE_DEMO_*` environment variables,
and §1.5 describes the fix: split the session-scoped **build** from a function-scoped
**publication**. No plant is needed for that — running the worker's own reproduction *in the
order it published* is the experiment, and green means the leak is closed.

**Result: ORDER-DEPENDENCE CLOSED.**

```
tests/test_transitions.py::test_the_shared_connection_is_the_one_db_py_opens        40.4 s
tests/test_row_factory_contract.py::test_the_production_connection_really_is_dict_row 50.5 s
tests/test_transitions.py::test_the_request_after_a_gate_run_is_not_a_503           12.2 s
3 tests, 0 failures, 0 errors, 103.1 s
```

The interleave that produced `assert 422 == 200` in W5's own document now passes in that
order. Two caveats a lead should carry:

* **This is the worker's own reproduction, not an independent one.** It is the strongest
  evidence available without re-deriving the defect from scratch, and it is weaker than the
  three plants above, where the harness put the defect back itself. A plant that reverts the
  `_w1_built` / `w1_database` split would be the equal of W3's and W4's cases; when I
  measured, `test_row_factory_contract.py` still carried the **session-scoped** fixture with
  the four `os.environ` assignments inside it, so the split was not yet in the tree to
  revert. It landed while this audit was running. **Adding that plant is one `Replace` in
  `scripts/qa/demo_suite_falsification.py` and it should be added before merge.**
* W5's document lists further dependencies it deliberately did **not** fix (§7 there),
  including the mirror-image `w4_database` publication. Those are unfalsified by
  construction: nothing changed, so nothing can be put back.

---

## 5 · The new test, and the defect it found on its first run

`verticals/mainline/apps/demo-api/tests/test_seed_covers_every_console_resource.py` parses
`RESOURCE_KEYS` out of `apps/console/src/data/resources.ts` — it does not restate it, because
a second copy of a list is a second thing to drift and that drift IS the defect — and drives
every GET resource the console declares against the seeded fixture database, requiring a
payload.

**On its first run against a cluster: 13 passed, 1 failed.** The failure is `silence`:

```
AssertionError: the console declares resource 'silence' and the deployed demo seed carries a
row the committed contract cannot express, so the reader REFUSES to render it:
mainline_meas.silence_receipt dec0de00-000a-4000-8000-000000000001 carries a boundary_proof
silence.schema.json cannot express: boundary_proof carries ['leaf_s', 'leaf_s_plus_1',
'source', 'synthetic'] where the contract declares ['leaf_s', 'leaf_s_plus_1']; undeclared
['source', 'synthetic'].
```

`verticals/mainline/db/seeds/demo/demo_permit.sql:161-171` seeds that `boundary_proof`, and
`git diff` shows the block **unchanged by this wave** — it is a standing defect, not a
regression. `reads.read_silence` is right to refuse: the contract is the authority, and a
reader that quietly dropped the two undeclared keys would be rendering a Proof of Exhausted
Recall that says something the database did not.

**I left the assertion where it is.** Narrowing this file to `NotFound` only would have made
it green, and it would have been the same act as reshaping a seed to match a constant: the
console tells a judge the resource exists, the resource answers with an error, and a test
that declines to notice is worse than no test. It is in `still_broken`, under the seed's
owner, with the measurement.

### 5.1 · What the plant proves the file is worth

`w6-console-declares-a-thirteenth-resource` adds a thirteenth GET resource to `resources.ts`
— exactly as `change_request` was once added — with nothing behind it in the seed. Control
green; planted red on two cases naming the new key. **This is the test that would have caught
W1's defect the day the resource was declared**, and the plant is the proof of that sentence
rather than the claim of it.

### 5.2 · A plant whose premise was wrong, recorded rather than deleted

I also tried to remove the custody checkpoint (`demo_world.sql` §8) so that `ledger` would
answer `NotFound`, to demonstrate the file's mechanism on a resource `conftest` does not
read. **The database refused the world instead:**

```
Failed: the deployed demo seed did not apply … demo_permit.sql did not apply [P0001]:
MAINLINE: recall policy anchor is not inside a cosigned checkpoint
```

That is a better answer than the one I was looking for, and it explains the shape of the
original gap: the demo world is welded so tightly that almost no seeded subject can vanish
silently — the seed simply stops applying. `change_request` could go missing precisely
because **nothing referenced it**: it was declared by the console, routed by the API, given a
table and a transition alphabet, and welded to nothing. The case was retired from the harness
rather than have its expectation rewritten to match its result, and the measurement is kept
here.

---

## 6 · The finding that made two of my own cases lie to me

**`w3_fixture.ready` certifies that a database was BUILT. It does not certify what it was
built FROM.** `demo_database` (`tests/conftest.py`) names its database
`w3_demo_api_<fingerprint>`, where the fingerprint is a SHA-256 over the migration chain
**and the seed files**, and it adopts any database of that name whose marker row matches.
There is no interlock. Two pytest sessions that compute the same fingerprint will
`DROP DATABASE IF EXISTS … CASCADE` and `CREATE DATABASE` on top of each other.

A plant that edits a seed changes that fingerprint. Measured, in this order:

1. **First attempt.** The planted run rebuilt, and something raced it:
   `190 of 271 migrations did not apply into w3_demo_api_0ecbb18f3666 … [3F000] cannot create
   "mainline.carriage" because the target database or schema does not exist`. The fixture
   turned that into a **skip**, and a skip is not a red — the case reported "NOT
   DEMONSTRATED" for a reason that had nothing to do with W1.
2. **Second attempt.** Both seed plants came back green in **25.7 s** against controls of
   25.4 s — the tell. The planted-fingerprint databases now existed *with the wrong
   contents*, built by the racing session after my plant was reverted:

   ```
   w3_demo_api_0ecbb18f3666   change_request=1   marker=('0ecbb18f3666',)
   w3_demo_api_12d77b2b80ec   ledger_checkpoint=1 marker=('12d77b2b80ec',)
   ```

   `0ecbb18f3666` is the fingerprint of a seed **with no change request in it**, and it holds
   a change request. The marker says the database is ready and the name says what it was
   built from; both are wrong, and the suite believes them.
3. **Third attempt.** The harness now drops `w3_demo_api_<fingerprint>` immediately after
   planting and again after reverting, so the plant reaches the database. W1 came back
   **DEMONSTRATED** in 185.8 s — the cost of the 271-migration rebuild the first two runs
   were quietly skipping.

Three consequences, none of which are mine to fix:

* **A developer editing a seed can get a green from a database built from a different seed.**
  That is the same class of silence as the CI lane that never ran: the board is green and
  nothing was measured.
* **A broken rebuild presents as a `pytest.skip`**, and the lead's own merge rule (§6.4) says
  a test that moves from failing to skipped is a regression. Here a *planted defect* moved a
  test from failing to skipped. `conftest.py:806` is the skip.
* The concurrent load was real and is worth naming: five `demo_suite_order.py shuffle`
  sessions plus a full suite were on the node while this audit ran. The interference is a
  property of the fixture, not of the neighbours.

---

## 7 · Whole-suite before and after

Both from the junit XML root element, `--crdb=reuse`, whole `verticals/mainline/apps/demo-api/tests`.

| | tests | failures | errors | skipped | seconds |
|---|---:|---:|---:|---:|---:|
| **before** `out/demo-suite-w6-falsification-audit-before.xml` | 502 | 8 | 64 | 1 | 1558.18 |
| **after** `out/demo-suite-w6-falsification-audit-after.xml` | 524 | 8 | 63 | 1 | 1567.55 |

`+22` tests: **14 are mine** (`test_seed_covers_every_console_resource.py` — two parse
guards and the twelve GET resources the console declares), and eight arrived from a
concurrent wave between the two runs.

Failure-by-failure, rather than by total:

| | |
|---|---|
| **new** | `test_seed_covers_every_console_resource::…[silence]` — §5, a standing defect this file surfaced on its first run |
| **gone** | `test_demo_guard_anonymous::test_the_four_refusals_leave_the_subject_and_every_row_count_unchanged` — it failed in the *before* run with `permits_that_appeared` while five `demo_suite_order.py shuffle` sessions were on the node, and passes in the *after* run when they had finished. Exactly the contamination W4 diagnosed; nothing was changed to make it pass |
| **errors** | 64 → 63. The one that went is a `psycopg.errors.SerializationFailure` on a fixture setup, also concurrency. The 63 that remain are all `KeyError: 'commit_v2'` — §2 |

**No test regressed.** The one new red is a real defect in the demo seed that no test could
see before, and the numbers either side are otherwise the same board.

The lead's baseline at `073dfea` was 444 · 375 · 5 · 1 · 63 / 1535.88 s. **The suite is no
longer 444 tests**, and comparing against that number now compares two different suites.
That is why every number in this document names the XML it came from — and it is a reason to
prefer the per-test diff above to the four-line summary, which is what let 63 identical
errors read as "the same as the baseline" for a whole wave.

---

## 8 · What I hand to the lead

1. **W1's 63 errors are still there under a new name** (`commit_v2`). §2.
2. **W2 landed nothing**; both defects reproduce. §3.
3. **The `silence` resource cannot be rendered**, and the seed is where it is wrong. §5.
4. **`demo_database` has no interlock and its marker does not describe its contents.** §6.
   This is the one I would fix first if the CI lane is going to run this suite more than once
   at a time — and the concurrent wave building `cluster-tests.yml` intends exactly that.
5. **The falsification cases are a command**, `scripts/qa/demo_suite_falsification.py`, with
   `--list`, `--dry-run` and `--case`. The CI wave's falsifiability job should be pointed at
   it. I did not add a workflow: `.github/workflows/` is theirs.
6. **W5's case is its own reproduction rather than a plant**, and one `Replace` would fix
   that. §4.3.

---

## 9 · Running it

```powershell
$env:TRAPPOINT_DSN = "postgresql://root@localhost:26257/defaultdb?sslmode=disable"
& .venv/Scripts/python.exe scripts/qa/demo_suite_falsification.py --list
& .venv/Scripts/python.exe scripts/qa/demo_suite_falsification.py --dry-run
& .venv/Scripts/python.exe scripts/qa/demo_suite_falsification.py
```

Exit 0 means every case reached its expected verdict. Exit 1 means **a claimed fix was not
demonstrated**, which is not the same thing as a broken build and must not be quieted with
`continue-on-error` or `|| true`. The junit XML for every control and every planted run, and
a `report.json`, land in `out/falsification/`.

**Read the wall-clock time as well as the verdict.** A seed plant that comes back in the same
time as its control did not rebuild anything, and §6 is what that means. The harness now
drops the fingerprinted database itself, so a healthy seed plant costs about 185 s and a
suspicious one about 25 s.

Three things a reviewer should refuse:

* a case whose `expect` strings were edited after seeing the run — that is fitting the
  expectation to the result, and it is the same act as reshaping a seed;
* a case added with no control, or with a control that is not green;
* a plant left in the tree. The harness proves the revert by SHA-256 per file and by a
  `git diff` digest scoped to the files it planted into; if either moves, it says so and
  exits 1.
