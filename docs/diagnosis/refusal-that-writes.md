<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# The refusal that wrote — what actually put the 117th row in `mainline.permit`

**Analyst:** `w4-refusal-that-writes` · **Measured 2026-08-13 on TRAPPOINT**, HEAD `073dfea`,
local CockroachDB CCL v26.2.5 (`trappoint-crdb`) · **Verdict: the four refused POSTs write
nothing. The row was minted by a second pytest process, and it is named below.**

---

## 0 · The board entry, and the answer in four lines

```
test_demo_guard_anonymous::test_the_four_posts_are_refused_with_the_permit_id_variable_unset
AssertionError: {'permit_rows_total': (116, 117)}
```

| question the lead set | answer |
|---|---|
| **1. Which POST wrote?** | **None of them.** All four are refused before any statement that could write, and `mainline.permit` is bit-for-bit identical across the drive window — measured by identity, not by count. |
| **2. Does the write precede or follow the refusal?** | Neither. There is no write on this path. |
| **3. Is the row the test's own or a neighbour's?** | A neighbour's — and not a neighbour in the same suite. `PTW-W4-56e0356353be`, opened `2026-08-13T10:07:37.554948Z`, minted by `verticals/mainline/apps/demo-api/tests/test_transitions.py:137` in a **second, concurrent pytest process** sharing the scratch database. |

**The writing statement, named with a file and a line:**

```
verticals/mainline/apps/demo-api/tests/test_transitions.py:137-141   _seed_permit()
    INSERT INTO mainline.permit (permit_id, site_id, site_role, external_ref, ref_name,
                                 horizon_at)
    VALUES (%s, %s, %s, %s, %s, now() + INTERVAL '30 days')
                                       -- external_ref = f"PTW-W4-{tag}"   (line 140)
```

reached through the `fresh_history` fixture (`test_transitions.py:237`). Its sibling
`bare_permit` (`test_transitions.py:267`) mints `PTW-BARE-…` the same way. Neither cleans
up, which is why `w_w4_api_transitions` held 116 permits when the baseline's failing test
read it and 217 fifty minutes later: 169 `PTW-W4-…`, 34 `PTW-BARE-…`, and one `PTW-PROOF-1`
— the demo subject itself, outnumbered 203 to 1 by fixture debris from runs that are over.

---

## 1 · Experiment 1 — drive the four POSTs and watch the table by identity

The test compares a **count**. A count cannot say *which* row appeared, which is why the
board entry was uninterpretable. The probe below drives the same four POSTs through the
same entry point on the same connection factory, with `MAINLINE_DEMO_PERMIT_ID` unset, and
compares the **set of `permit_id`s**:

```
database=w_w4_api_transitions  subject=199adc10-…  check=db736483-…
drive window: 0.047s
outcomes: {'merge_permit':      (423, 'demo_subject_unidentified'),
           'suspend_permit':    (423, 'demo_subject_unidentified'),
           'materialise_checks':(423, 'demo_subject_unidentified'),
           'sign_disposition':  (423, 'demo_subject_unidentified')}
permit rows before=217 after=217
  mainline.permit is bit-for-bit where it was found
```

The guard is correct on all four, and the drive window is **47 milliseconds**. Nothing on
this path writes, and the code says why:

* `transitions.py:1235-1239` — for the three `permit_id`-addressed resources the guard runs
  in `handle_transition` **before** the handler is entered, so `_merge_permit`,
  `_suspend_permit` and `_materialise_checks` are never called at all.
* `transitions.py:1036-1039` — `sign_disposition` is addressed by `check_id`, so its guard
  runs inside `_sign_disposition` after `_CHECK_SQL` resolves the obligation to its permit.
  Every statement issued before it is a read — two `resolve_credential_id` lookups, the
  `SET TRANSACTION ISOLATION LEVEL` in `_prepare`, and `_CHECK_SQL`. The
  `INSERT INTO mainline.disposition`
  (`transitions.py:1055`) is below the guard, and `conn.rollback()` precedes the return.
* `_borrowed` (`transitions.py:287`) rolls back and restores `autocommit` in one `finally`,
  and `_prepare` (`transitions.py:346`) is a tripwire that raises on an autocommit
  connection. Both were correct as they stood; **neither needed a change and neither got
  one.**

## 2 · Experiment 2 — name the 117th row

`mainline.permit` carries `opened_at TIMESTAMPTZ NOT NULL DEFAULT now()`
(`db/migrations/0050_permit.sql:89`), and the rows are still in the scratch database, so the
baseline run is reconstructable rather than merely arguable. Taking the suite start from
`out/demo-suite-baseline.xml` (`timestamp=2026-08-13T20:02:54.918075+10:00`) and summing the
per-case `time` attributes places the failing test at

```
10:07:03.405Z  →  10:07:43.829Z
```

and exactly one permit was opened inside it:

```
10:07:37.554948Z   PTW-W4-56e0356353be   56e03563-53be-4a91-8dc3-147c8caf503c
```

## 3 · Experiment 3 — it was a different process, and the proof is a fingerprint

Twenty-six permits were opened during the baseline's 1535 s. They fall into two blocks with
**identical composition, identical order and identical inter-arrival gaps**, offset by
950.7 s:

| # | block A | gap | block B | gap | ref kind |
|---|---|---|---|---|---|
| 1 | 10:04:55.787 | — | 10:20:46.494 | — | `PTW-W4-` |
| 2 | 10:05:16.699 | +20.9 | 10:21:07.400 | +20.9 | `PTW-W4-` |
| 3 | 10:07:37.554 | +140.9 | 10:23:28.117 | +140.7 | `PTW-W4-` |
| 4 | 10:07:58.739 | +21.2 | 10:23:48.484 | +20.4 | `PTW-W4-` |
| 5 | 10:08:18.366 | +19.6 | 10:24:10.492 | +22.0 | `PTW-W4-` |
| 6 | 10:08:39.639 | +21.3 | 10:24:30.176 | +19.7 | `PTW-W4-` |
| 7 | 10:09:00.979 | +21.3 | 10:24:51.602 | +21.4 | `PTW-BARE-` |
| 8 | 10:09:20.276 | +19.3 | 10:25:12.466 | +20.9 | `PTW-W4-` |
| 9 | 10:09:41.560 | +21.3 | 10:25:32.261 | +19.8 | `PTW-W4-` |
| 10 | 10:10:02.450 | +20.9 | 10:25:53.257 | +21.0 | `PTW-BARE-` |
| 11 | 10:11:15.553 | +73.1 | 10:27:06.100 | +72.8 | `PTW-W4-` |
| 12 | 10:11:47.935 | +32.4 | 10:27:38.715 | +32.6 | `PTW-W4-` |
| 13 | 10:12:09.131 | +21.2 | 10:27:59.828 | +21.1 | `PTW-W4-` |

That is one file — `test_transitions.py` — executed twice. **Block B is the baseline's own
run:** the same junit XML puts its first `test_transitions` case at `10:19:15Z`, and block B
begins 91 s later. **Block A cannot be:** at `10:04:55Z` the baseline was 121 s in, four
cases into `test_demo_guard_anonymous`, and every module it had reached by the end of block A
at `10:12:09Z` — `test_credentials`, `test_demo_guard_anonymous`, `test_envelope`,
`test_gate_run`, `test_logbudget`, `test_ratelimit` and the first minute of `test_reads` —
contains no statement that inserts a permit. `grep -n 'INSERT INTO mainline\.permit'` over
the whole app returns `test_transitions.py:138` and `test_transitions.py:268` and nothing
else.

So a second pytest process was running `test_transitions.py` against
`w_w4_api_transitions` while the lead measured the baseline, and row 117 is its
`fresh_history` fixture.

## 4 · Why this was inevitable, and where the actual defect lives

```
verticals/mainline/apps/demo-api/tests/test_gate_run.py:143
    SCRATCH_DB = os.environ.get("MAINLINE_W4_DATABASE", "w_w4_api_transitions")
```

A **fixed default name**. Every pytest process on this machine adopts the same scratch
database — the fixture is written to reuse it deliberately, because rebuilding costs 271
migrations — and `test_demo_guard_anonymous`'s snapshot counts `mainline.permit`
**globally** (`_SNAPSHOT_SQL`, the `SELECT count(*) FROM mainline.permit` clause). The
global clause is right: a transition that created a subject instead of moving one would
otherwise slip past a per-subject diff. But it is an assertion about a whole database that
this test does not own, and the wave's own execution model — six workers, one node, §4 of
`docs/leads/demo-suite-plan.md` telling each of them to run the full suite — guarantees a
foreign writer.

**Corroboration, from my own before-run** (`out/demo-suite-w4-before.xml`, same HEAD, same
command, 20:39–21:05): with another worker's suite live on the node, the contamination got
worse and it got broader. Four results moved that have nothing in common except a shared
database:

| result | lead's baseline | w4 before-run | alone, isolated db |
|---|---|---|---|
| `test_the_four_posts_are_refused_…_unset` | fail `(116, 117)` | fail `(203, 204)` | **pass** |
| `test_the_four_refusals_leave_…_unchanged` | pass | fail **`(181, 192)`** | **pass** |
| `test_gate_run_is_reachable_through_handle_transition` | pass | fail *"the affected tables are NOT byte-identical before and after the run"* | **pass** |
| `test_suspending_a_merged_permit_commits` (+1 more) | pass | error `psycopg.errors.SerializationFailure: restart transaction: TransactionRetryWithProtoRefreshError` | **pass** |

Two of those deserve to be read twice. **`(181, 192)` is eleven permits in one snapshot
window** — the four POSTs it brackets take 47 ms and issue no write at all. And a
**`40001 RETRY_SERIALIZABLE` on a single-node local Docker node**, which the platform notes
in this repository correctly say never happens there, happens the moment two suites contend
over one scratch database. Neither red is about the product; both are the same foreign
writer seen through different assertions.

The lead's baseline caught only one of the two count tests because block A happened to fall
in its 140.9 s gap while the other one ran. That is the definition of a coin toss.

### What was changed, and what was not

`test_demo_guard_anonymous.py`'s snapshot now carries `permit_ids` — the **set** of
identifiers — beside the existing `permit_rows_total`. This is strictly stronger than the
count it sits next to (a count cannot see an INSERT paired with a DELETE) and it cannot
turn any red green. What it changes is what a red *says*: `changed()` reports the rows that
appeared with their `external_ref`, their `opened_at`, and the fixture that mints that
prefix, so the next reader is told in one line whether the API wrote the row or a stranger
did. The assertion is still `after == before` over every field, `mainline.permit` included.

**Nothing was excluded from the snapshot, no comparison was loosened, no ceiling moved, and
the test was not given a private database.** The shared world is the property.

### What is still open, and whose it is

`SCRATCH_DB`'s fixed default is in `test_gate_run.py`, which belongs to **W5**. Two
remedies exist and both are W5's to choose: give the scratch database a per-process
discriminator, or state in `docs/ci/demo-suite-order.md` that concurrent full-suite runs
against one node are unsupported and have the wave serialise them. Until one lands, **every
worker's before/after numbers in this wave are contaminated by every other worker's**, and
the two global-count tests are a coin toss. That is a finding about the wave's methodology,
not only about this test.

---

## 5 · The ten-second connect — why `/v1/health` "takes 10.1 s" and the suite takes 25 minutes

Found while timing the drive window, and it is not this test's problem alone.

```
getaddrinfo("localhost", 26257) -> [AF_INET6 ('::1', 26257), AF_INET ('127.0.0.1', 26257)]

psycopg.connect("…@127.0.0.1:26257…", connect_timeout=20)   ->  OK   0.008 s
psycopg.connect("…@localhost:26257…",  connect_timeout=20)   ->  OK  20.031 s
psycopg.connect("…@localhost:26257…",  connect_timeout=15)   ->  OK  15.071 s
psycopg.connect("…@localhost:26257…",  connect_timeout=10)   ->  OK  10.102 s
```

`localhost` resolves to `::1` **first**; the container publishes on IPv4 only and the IPv6
attempt is black-holed rather than refused, so libpq waits the **whole** `connect_timeout`
before falling back to `127.0.0.1`. The elapsed time equals the timeout, exactly, every
time. `db.CONNECT_TIMEOUT_SECONDS` is 10 (`db.py:92`), so **every connection this suite
opens against the runbook DSN costs ten seconds**.

That single fact explains, arithmetically, the whole timing shape of the baseline:

| baseline case | connections it opens | measured |
|---|---|---|
| `test_the_uuid5_fallback_names_a_permit_that_is_not_in_this_database` | 1 | 10.081 s |
| `test_the_guard_does_not_refuse_traffic_that_is_not_the_demo_subject` | 1 | 10.101 s |
| `test_every_committing_post_is_refused_…` (×4) | 2 | 20.15–20.22 s |
| `test_the_four_posts_are_refused_with_the_permit_id_variable_unset` | 4 | 40.424 s |

**This is almost certainly W2's third failure in its entirety.**
`test_health_is_200_with_a_real_schema_fingerprint` fails `assert 10.103 < 5.0`, and
`health()` opens exactly one connection (`health.py:258`, `db.connection(dsn=dsn)`). 10.103
is 10.1, not a schema-fingerprint cost, and no amount of narrowing the catalog query will
move it. The repository's own default DSN is already correct —
`test_gate_run.py:142`, `DEFAULT_DSN = "postgresql://root@127.0.0.1:26257/…"` — it is
`TRAPPOINT_DSN`, spelled `localhost` in the runbook, that pays the tax. **Nothing in the
product is at fault and nothing in the product was changed for it**; on the deployed Lambda
the host is a Cloud A-record and there is no IPv6 fallback to wait for. The remedy is one
character class in the runbook: `127.0.0.1`, not `localhost`.

Reported here rather than fixed because `health.py` and `test_reads.py` belong to W2 and
§4's command belongs to the lead.

---

## 6 · Session hygiene — two `mainline-demo-api` sessions still open

Confirmed, and still true at the time of writing:

```
application_name   client_address       last_active_query      session_start        status
mainline-demo-api  172.20.0.1:50818     ROLLBACK TRANSACTION   2026-08-13 05:58:55Z  IDLE
mainline-demo-api  172.20.0.1:56618     ROLLBACK TRANSACTION   2026-08-13 05:59:15Z  IDLE
```

`ROLLBACK TRANSACTION` is the signature of `transitions._borrowed`'s `finally`
(`transitions.py:333`) — these connections last served a transition and were then abandoned.

**It is not an unclosed code path.** Every `db.connection()` in `src/` has a matching
`db.close()`: `app.py:484/488/514/592`, `health.py:258/284`. `db.close()` itself is
idempotent and suppresses on the way out (`db.py:350-359`). What is missing is a **process**:
a pytest run killed mid-flight never runs its fixture teardown, and the client address
`172.20.0.1` is Docker Desktop's port proxy, which holds the server side of the socket open
after the client is gone — so the node never learns the peer died. §0.3 of the lead's plan
records two runs stopped by hand on this machine; the two session starts are 20 s apart,
which is two processes and not one.

**Consequence, and why it is worth naming anyway.** On a warm Lambda this is one idle
connection and harmless by design. On a shared cluster each one is an
idle-in-transaction `40001` amplifier that no alarm in this repository can see. The remedy
is `idle_in_transaction_session_timeout` on the cluster or the role, which is an operator
setting and not a code change; nothing in `db.py` can close a socket its process no longer
exists to close.

## 7 · `transitions.py:1255-1261` answers `503 database_unreachable` to a serialization restart

Recorded, **not fixed** — the lead's brief asks for it to be noted, and it needs a ruling.
(The brief cites `transitions.py:1142`; at `073dfea` that line is inside `_demo_gate_run` and
the handler in question has moved to **1255-1261**. Same defect, current address.)

`psycopg.errors.SerializationFailure` inherits from `psycopg.OperationalError`
(`divergence-04-connection-semantics.md` §F-2 records the reproduction). `handle_transition`'s
last handler is

```python
except psycopg.OperationalError as exc:                     # transitions.py:1255
    ...
    return _error(503, "database_unreachable", …)           # transitions.py:1261
```

so a `40001` raised by any statement **outside** an inner `except psycopg.Error` — and there
are several: `_permit_epoch` (`:485`), `_prepare` (`:346`), `_demo_subject_is_established`
(`:398`), `resolve_credential_id` (`:1026`), and every `conn.commit()` — is reported to the
caller as *"database_unreachable"*. That sentence is **false** (the database answered, and
answered with a decision) and **unactionable** (the correct advice for `40001` is "attempt
again or do not", which is what the `retry` outcome already says, with a proper envelope,
at `_refused` → `transitions.py:508-525`).

It is left alone deliberately. `test_transitions.py:1036`
(`test_a_40001_escaping_the_beats_does_not_leak_the_flag`) asserts the present behaviour
**on purpose**, and says so: *"asserted here as the behaviour it IS, not as the behaviour it
should be"*. Correcting the taxonomy means editing that expected value, which §6.3 of the
plan has the lead read line by line — rightly. It also matters only on a managed cluster:
single-node Docker never issues `RETRY_SERIALIZABLE`, so this is invisible locally and live
in Cloud `mainline_demo`, which is exactly the shape of defect this repository keeps
finding. **Recommendation to the lead: catch `psycopg.errors.SerializationFailure` before
`psycopg.OperationalError` in `handle_transition` and return the existing `retry` envelope,
and update `test_transitions.py:1058-1059` with that ruling written down.**

---

## 8 · Falsification

A fix nobody can put back is a fix nobody has demonstrated. Since the product needed no
change, what had to be falsified is the **test**: does it actually catch a refusal that
writes?

**The plant.** In `transitions._demo_guard`, immediately before the
`demo_subject_unidentified` return — i.e. a handler that writes and *then* refuses, which is
question 2 of the brief made real:

```python
    conn.execute(
        "INSERT INTO mainline.permit (permit_id, site_id, site_role, external_ref, "
        "ref_name, horizon_at) SELECT gen_random_uuid(), p.site_id, p.site_role, "
        "'PTW-PLANT-' || substr(gen_random_uuid()::STRING, 1, 8), 'refs/permits/plant', "
        "now() + INTERVAL '30 days' FROM mainline.permit p LIMIT 1"
    )
    conn.commit()
```

**Result — recorded in §9.** The test goes red, and with `permit_ids` in the snapshot the
red now names the row and reports that *no fixture in this suite mints that external_ref —
this is the API's own write*, which is precisely the sentence the `116 != 117` red could not
produce.

## 9 · Measurements, in order

| # | what | result |
|---|---|---|
| 1 | four POSTs, identity diff, shared db | 217 → 217, all four `423 demo_subject_unidentified`, 0.047 s |
| 2 | the row inside the failing test's window | `PTW-W4-56e0356353be` @ `10:07:37.554948Z` |
| 3 | two-block fingerprint over the baseline | two runs of `test_transitions.py`, 950.7 s apart |
| 4 | `test_demo_guard_anonymous.py` alone, isolated scratch db | **13 passed** — see §10 |
| 5 | the plant of §8, same file, same database | **red, naming the planted row** — see §10 |
| 6 | `test_transitions.py` alone vs in suite | see §11 |

## 10 · The isolated run, and the plant

Both run against `w_w4_refusal_that_writes` — a scratch database this worker owns, reached
by `MAINLINE_W4_DATABASE`, which the fixture already supports (`test_gate_run.py:143`). It
isolates this measurement from the **other five workers**; it is not a change to the test,
and within the run the scratch database is still shared by `test_gate_run.py`,
`test_transitions.py` and `test_demo_guard_anonymous.py` exactly as before.

**Clean:**

```
$env:TRAPPOINT_DSN       = "postgresql://root@127.0.0.1:26257/defaultdb?sslmode=disable"
$env:MAINLINE_W4_DATABASE = "w_w4_refusal_that_writes"
pytest .../tests/test_demo_guard_anonymous.py --crdb=reuse -q

13 passed in 66.95s          (cold: 271 migrations + seed)
13 passed in  0.49s          (warm, after the fixture database was built)
```

All thirteen, including **both** global-count tests. `permit_rows_total` in this database is
`1` — one seeded subject, no accumulated fixture debris — so the assertion has nowhere to
hide.

**Planted** — `_demo_guard`, immediately before the `demo_subject_unidentified` return, same
file, same database, nothing else changed:

```
FAILED test_demo_guard_anonymous.py::test_the_four_posts_are_refused_with_the_permit_id_variable_unset
E   AssertionError: {'permit_rows_total': (1, 5),
E    'permits_that_appeared': ["2889a0d4-6e63-4d85-b58f-3b7464ec66c4
E        external_ref='PTW-PLANT-…' opened_at=2026-08-13 11:07:20.736273+00:00
E        minted by no fixture in this suite mints that external_ref
E                  — this is the API's own write"]}
verticals/mainline/apps/demo-api/tests/test_demo_guard_anonymous.py:551: AssertionError

1 failed, 12 passed in 0.76s
```

Three things this establishes, and the third is the one that matters:

1. The test **does** catch a refusal that writes — one red, and it is the right test.
2. It catches it on the branch the plant is on and nowhere else:
   `test_the_four_refusals_leave_the_subject_and_every_row_count_unchanged` stayed green,
   because with `MAINLINE_DEMO_PERMIT_ID` **set** the guard returns
   `demo_subject_write_protected` above the plant and never reaches it. A plant that turned
   everything red would have proved much less.
3. **The red now names its author.** Compare it with `{'permit_rows_total': (116, 117)}`,
   which is the same defect class reported by the same test three hours earlier and told
   nobody anything. That sentence — *"no fixture in this suite mints that external_ref — this
   is the API's own write"* — is the difference between a board entry and a diagnosis.

Reverted, and the revert proven by re-running the same file: **13 passed in 0.49 s**, and
`git diff` over `transitions.py` and `db.py` is empty. The four `PTW-PLANT-…` rows the plant
committed were deleted from `w_w4_refusal_that_writes` afterwards; a falsification harness
that leaves its defect behind is worse than none.

### The plant escaped, and that is my error, reported rather than tidied away

**I applied the plant to the shared working tree while other workers were running.** Six
workers share one checkout of `D:/CoackroachDBxAWS/mainline`, and a `pytest` session imports
`transitions.py` **once**, at collection. So for the ~45 s the plant existed on disk, any
other worker's session that imported the module got it — and kept it in memory for the rest
of its run, after my revert had removed it from the file.

It did. Twelve `PTW-PLANT-…` rows landed in the **shared** `w_w4_api_transitions`, in three
batches of four:

```
11:07:31.500  11:07:31.511  11:07:31.522  11:07:31.541     PTW-PLANT-…
11:08:05.423  11:08:05.435  11:08:05.444  11:08:05.456     PTW-PLANT-…
11:12:31.193  11:12:31.206  11:12:31.216  11:12:31.229     PTW-PLANT-…
```

My plant ran once, at `11:07:20`, in `w_w4_refusal_that_writes`. **None of those twelve rows
are mine to have written**, and the third batch is four minutes after the revert — a session
that had already imported the planted module. One of them then showed up inside my own
after-run's snapshot window, which is how it was found.

**All twelve have been deleted** (`DELETE … WHERE external_ref LIKE 'PTW-PLANT-%'`, 12 rows,
verified 0 remaining), every database on the node was scanned and only that one was
affected, and `transitions.py` contains no occurrence of `PTW-PLANT`.

**Any worker whose run overlapped 11:07–11:13 UTC on 2026-08-13 should re-check a red that
mentions an unexpected permit**, and W6 should note the method: §W6 of the plan says *"put it
back by hand in a scratch copy of the working tree"*, and it says that for exactly this
reason. I planted in place. That was the wrong call and it cost twelve rows in somebody
else's fixture — a small instance of the same class this whole document is about, which is
that a shared resource with no discriminator makes one worker's experiment another worker's
evidence.

## 11 · `test_the_request_after_a_gate_run_is_not_a_503` — alone and in suite, for W5

The wave brief sent this worker after that test; the lead's baseline records it **passing**
and it is not on the board (§0.2 of the plan). What follows is the measurement W5 asked
for, and nothing more — W5 owns settling it under seeded randomised order.

| run | database | `…gate_run_is_not_a_503` | `…sign_disposition_is_not_a_503` |
|---|---|---|---|
| lead baseline, in suite | shared `w_w4_api_transitions` | **pass** 12.053 s | **pass** 20.741 s |
| w4 before-run, in suite | shared `w_w4_api_transitions` | **pass** 12.027 s | **pass** 20.671 s |
| w4, `test_transitions.py` **alone** | isolated `w_w4_refusal_that_writes` | **pass** 2.142 s | **pass** 0.522 s |

`pytest .../test_transitions.py --crdb=reuse -q` alone → **33 passed in 11.35 s**, nothing
skipped. Junit XML at `out/w4-transitions-alone.xml`; the two in-suite runs are
`out/demo-suite-baseline.xml` and `out/demo-suite-w4-before.xml`.

**It does not reproduce, in either direction, in four independent runs.** The orchestrator's
board is the only place it has ever been seen red, and §0.2 of the plan already records that
the lead could not reproduce it either.

**What W5 should chase instead.** The order-dependent failure in `test_transitions.py` is
real, and it is a different test: `test_gate_run_is_reachable_through_handle_transition`
passed alone, passed in the lead's baseline, and **failed in my before-run** with

```
['the affected tables are NOT byte-identical before and after the run;
  the transaction was supposed to persist nothing']   assert 'NOT PROVEN' == 'PROVEN'
```

Same shape as the two count tests: an assertion that a shared table is unchanged across a
window, broken by a writer the test does not own. Under `--crdb=reuse` on a node with one
other suite live, `test_transitions.py` also produced two setup errors
(`SerializationFailure`) that neither other run has. So there **is** an order/isolation
defect in this module — it is just not the one the wave brief named, and the timings above
say the difference between the two hypotheses is measurable rather than arguable. The
seeded-order harness W5 is building will separate them; point it at
`w_w4_api_transitions`'s fixed name first.

Note also, for W5's cost table: the same 33 tests take **11.35 s** against `127.0.0.1` and
**~380 s** in-suite against `localhost`. Almost all of that difference is §5, not the tests.

---

## 12 · Whole-suite numbers, before and after — and why the pair is weaker than it looks

Both runs: `pytest verticals/mainline/apps/demo-api/tests --crdb=reuse -q --tb=line
--timeout=180`, `TRAPPOINT_DSN` spelled `localhost`, shared `w_w4_api_transitions` — §4 of
the plan, verbatim, so they are comparable with the lead's baseline.

| | tests | passed | failed | errors | skipped | seconds |
|---|---:|---:|---:|---:|---:|---:|
| lead's baseline (`out/demo-suite-baseline.xml`) | 444 | 375 | 5 | 63 | 1 | 1535.60 |
| **before** (`out/demo-suite-w4-before.xml`) | 444 | 371 | 7 | 65 | 1 | 1540.36 |
| **after** (`out/demo-suite-w4-after.xml`) | **445** | **377** | **3** | **64** | 1 | 1550.90 |

`test_the_four_posts_are_refused_with_the_permit_id_variable_unset` is **green in the after
run**, and green in every isolated run. It is off the board.

**Read the rest of that table with care, because three things moved that are not mine.**

1. **The tree changed underneath the pair.** `tests=444` before, **`445` after**: another
   worker added a test to this suite between my two runs. The two
   `test_refusal_row_factory` failures also disappeared, which is W3's fix landing, and one
   `cr_id` error went with it. A worker who reported "+6 passed, −4 failed" as their own
   work would be claiming three other people's. I am not.
2. **The remaining reds are the same coin toss, still flipping.**
   `test_the_four_refusals_leave_the_subject_and_every_row_count_unchanged` failed in both
   runs — `(181, 192)` before, `(336, 340)` after — and
   `test_gate_run_is_reachable_through_handle_transition` failed before and passed after
   without anyone touching it. The `test_transitions` setup `SerializationFailure` moved to
   a different test. Nothing in that paragraph is a product change.
3. **The after run's version of that red is the new message doing its job in the wild:**

   ```
   AssertionError: {'permit_rows_total': (336, 340),
    'permits_that_appeared': ["289d9a96-… external_ref='PTW-PLANT-…'
        opened_at=2026-08-13 11:12:31.206216+00:00
        minted by no fixture in this suite mints that external_ref
                  — this is the API's own write"]}
   ```

   It named the row, and the row turned out to be the escaped plant of §8 — which is how the
   escape was discovered at all. The old message would have said `(336, 340)` and nothing
   else, and I would have filed it as one more anonymous foreign write.

   **One honest limitation of that sentence.** "This is the API's own write" is true of the
   row and false about *whose* API: the write was made by a different process running a
   planted build. No in-database attribution of a writing session exists, so the message
   reports the row's nature and stops there rather than guessing at a culprit. That is the
   correct place to stop, and it is why §4's remedy is isolation and not a cleverer message.

`test_reads::test_health_is_200_with_a_real_schema_fingerprint` failed in both, at
`10.0908` and `10.1011` — see §5; that is one IPv6 connect attempt, twice, to the tenth of a
second.
