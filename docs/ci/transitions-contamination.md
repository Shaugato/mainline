<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# `test_transitions.py`: how wide the contamination really is — measured, not inherited

**Worker:** W4, lane-honest wave · **Ruling requested by** `docs/leads/lane-honest-plan.md`
**R7** (*"Justify 3 or widen it … 'The brief said 13' is not a measurement"*).
**Date:** 2026-08-14. **HEAD:** `eefae1c`, working tree dirty and **moving** — see §2.
**Host:** TRAPPOINT, CockroachDB CCL v26.2.5 on `127.0.0.1:26257`, **one node**.
**Interpreter:** `.venv/Scripts/python.exe` — pytest 9.1.1, pytest-random-order 1.2.0,
psycopg 3.3.4.

**Every number in this document was read from the `<testsuite>` attributes and the
`<testcase>` children of a `--junitxml` this worker produced, one XML per run, each into its
own path. Nothing was taken from a terminal scroll.** The per-run records, the per-node-id
tallies, the sha256 of every XML and the full command line of every invocation are in
[`evidence/qa/transitions-stability.json`](../../evidence/qa/transitions-stability.json).

**This worker edited no test, no fixture, no seed, no workflow and no inventory.**
`qa/cluster-known-red.json` belongs to W3 and is untouched here; §7 is the handoff.

---

## 0 · The ruling, in five sentences

1. **33 runs, 1 089 executions of the 33 node ids in this module**, plus one probe that built
   the first scratch database and is listed in §2 but not tallied. The 33: **8** isolated,
   **3** in-suite, **5** randomised, **8** concurrent (4 sharing one database, 4 not),
   **3** rebuild-vs-adopt, **3** scratch-database warm-ups, and the wave's **BEFORE**,
   **AFTER** and **AFTER2** whole-suite readings.
2. **The tree moved under the battery**, sharply and datably, and the runs split into two
   worlds. In **world 1** — 16 runs, 528 executions — the failing family of this module is
   **2 node ids, each failing exactly once, both in the one run of that world that BUILT a
   scratch database rather than adopting one**. Fifteen of the sixteen runs had **zero red in
   this module**, including **all 8 isolated, all 3 in-suite and all 3 randomised**.
3. In **world 2** — 17 runs, 561 executions, after another lead's in-flight
   `mainline.defeater_option` work landed at 09:24 — **9 node ids fail 17 of 17**. A failure
   present in *every* run of a world and *no* run of the other is **deterministic**, and a
   deterministic red is not an unstable one. It is not this wave's to fix (R10).
4. The **only** non-deterministic signal in 1 089 executions is `40001 RETRY_SERIALIZABLE`
   raised in **SETUP**: **12 occurrences over 6 distinct node ids in the 4 runs that shared a
   scratch database, and 0 occurrences in the 4 runs started at the same instants that did
   not** — plus 0 in all 25 other runs. All 6 route through `_seed_permit`.
5. **RULING: do not widen the `unstable` list to a set of node ids, and do not call 3
   correct either — the list is aimed at the wrong axis.** The three entries stay (R7 forbids
   deleting them on passes), their `runs_observed` rises by the passes measured here, and
   their `reason` is re-grounded on the mechanism that was actually reproduced. §6 gives the
   counts both ways so W3 can record either without re-measuring.

---

## 1 · The module, counted

`verticals/mainline/apps/demo-api/tests/test_transitions.py`, sha256 `38dbfbbc…`, mtime
2026-08-13 18:31:38 — **byte-identical across every run in this document**. So is
`test_gate_run.py` (which owns `w4_database` and `SCRATCH_DB`) and so is
`scripts/proof/gate_refusal.py` (which seeds the scratch database). Counted from the
module's own AST, not from a brief:

| | |
|---|---:|
| test functions defined | **30** |
| node ids collected (one function is parametrised over 4 resources) | **33** |
| take `w4_conn` | **20** |
| take `shared_conn` | **8** |
| take **`fresh_history`** | **11** |
| take no database-backed fixture at all | **2** |

The plan's §R7 says *"30 tests, of which 21 take the shared `w4_conn`"*. The count is **20**,
not 21; the other database-backed family is `shared_conn`, which 8 take. The difference does
not change any conclusion and is recorded because a number in a ruling should be checkable.

**`fresh_history` is the fixture that matters**, and it is not the one the plan pointed at.
Its body is `_seed_permit` (`test_transitions.py:116-226`): **thirteen client statements —
one `SELECT`, eight `INSERT`s and two `INSERT`/`UPDATE` pairs in a loop — inside ONE explicit
transaction, ending in a single `commit()` at line 225 with no retry of any kind.** Eleven
node ids take it. That is the structurally exposed family, and §4 shows it is the one that
actually moves.

---

## 2 · The tree moved while this was measured, and the boundary is sharp

This is recorded first because every number after it depends on it, and because a single
stability figure taken across a moving tree would be a fiction.

Read from the filesystem after the battery, with the run timestamps from the JUnit
`timestamp` attributes (all local, +10:00):

| time | what happened |
|---|---|
| 09:15:12 | probe run — fresh build of `w_w4stab_a`, **33/33 green** *(not tallied; it exists to build the database)* |
| 09:17:30 | **BEFORE** whole-suite reading: 528 / 1 failed / 0 errors / 1 skipped |
| 09:18:41 – 09:20:19 | **A01–A08**, the 8 isolated runs — **33/33 green, all eight** |
| 09:19:29 | *another lead rewrites* `verticals/mainline/db/seeds/demo/demo_world.sql` |
| 09:20:45 – 09:22:20 | **B01–B03**, the 3 in-suite runs — 0 red in this module |
| 09:21:26 | *another lead lands* `src/mainline_demo_api/defeaters.py` (**new module**) |
| 09:23:07 | *another lead lands* `src/mainline_demo_api/retry.py` (**new module**) |
| 09:23:15 – 09:23:44 | **C01–C03**, the 3 randomised runs — 0 red in this module |
| 09:23:57 | **W01** — fresh build of a second scratch database — **2 failed** |
| **09:24:25** | *another lead rewrites* `src/mainline_demo_api/gate_run.py` ← **the boundary** |
| 09:25:39 | *another lead rewrites* `src/mainline_demo_api/transitions.py` |
| 09:25:56 – 09:32:07 | W02, W03, D×4, E×4, F×2 — **9 red in this module, every run** |
| 09:33:20 – 09:35:54 | **G01–G03**, the rebuild-vs-adopt A/B/A — **9 red, all three** |
| 09:33:33 | *another lead lands* `tests/test_defeaters.py` — collection 528 → **556** |
| 09:36:31 | **AFTER** whole-suite reading: 556 / 21 failed / 13 errors / 10 skipped |
| 09:44:17 | **AFTER2**, taken after both of this worker's files were written: 556 / 21 / 13 / 10 |

**The single cleanest pair in this whole document:** `w_w4stab_a` is one database, built once
at 09:13 and never rebuilt. Between 09:15 and 09:23:44 it produced **zero red in this module
in fifteen consecutive runs** — twelve of the module alone, each **33/33 green** (the probe,
A01–A08 and C01–C03), and three whole-suite (B01–B03). Against the same database at 09:31:13
(F01), 09:33:20 (G01) and 09:35:54 (G03) it produced **9 of 33 red**. Same database, same test
file, same flags, same host, one process at a time. **Only the demo-api source changed.**

Arm **G** was run to rule out the obvious competing explanation — that a database *adopted*
from before the change behaves differently from one *built* after it. It does not: G01
(adopt) **9**, G02 (`MAINLINE_W4_REBUILD=1`, fresh build) **9**, G03 (adopt) **9**. Adoption
is not the variable. The source is.

**This is not this wave's defect and nothing here was worked around.** The work landing is
the seed lead's answer to blocker 1 (`mainline.defeater_option` holds zero rows); R10 puts it
out of scope. It is reported because it is the reason the AFTER number moved, and because a
worker who quietly averaged across it would have published a fiction.

---

## 3 · The measured family, by world

"Family" = every node id in this module failed or errored in at least one recorded run.

### World 1 — 16 runs, 528 executions, before the 09:24:25 boundary

| node id | failed / observed |
|---|---:|
| `test_gate_run_is_reachable_through_handle_transition` | **1 / 16** |
| `test_the_request_after_a_gate_run_is_not_a_503` | **1 / 16** |
| *every other node id in the module* | **0 / 16** |

**Family size: 2.** Both failures are in the *same single run* — **W01**, the only run of
this world that built a fresh scratch database — and both carry the same message:
`beat 4 (admit): expected {'outcome': 'admitted', 'sqlstate': '00000'}, observed
outcome='error'`. W01 started 28 seconds before `gate_run.py` was rewritten and 50 seconds
after `retry.py` appeared, so this worker **cannot cleanly attribute it** and does not.

What this world does say, cleanly: **all 8 isolated runs, all 3 in-suite runs and all 3
randomised runs were 33/33 green, and all three `unstable` node ids passed in every one of
them.**

### World 2 — 17 runs, 561 executions, after the boundary

| node id | failed / observed | takes `fresh_history` |
|---|---:|:--:|
| `test_a_40001_escaping_the_beats_does_not_leak_the_flag` | **17 / 17** | |
| `test_a_gate_run_hands_the_shared_connection_back_in_autocommit` | **17 / 17** | |
| `test_gate_run_is_reachable_through_handle_transition` | **17 / 17** | |
| `test_merging_an_already_merged_permit_is_refused_by_the_epoch_pin` | **17 / 17** | ✓ |
| `test_sign_disposition_hands_the_shared_connection_back_in_autocommit` | **17 / 17** | ✓ |
| `test_sign_disposition_then_merge_commits` | **17 / 17** | ✓ |
| `test_suspending_a_merged_permit_commits` | **17 / 17** | ✓ |
| `test_the_request_after_a_gate_run_is_not_a_503` | **17 / 17** | |
| `test_the_request_after_a_sign_disposition_is_not_a_503` | **17 / 17** | ✓ |
| `test_materialise_checks_issues_a_receipt_and_moves_the_subject` | **4 / 17** | ✓ |
| `test_a_one_word_clearance_is_refused_by_the_api_not_the_gate` | **2 / 17** | ✓ |
| `test_every_outcome_hands_the_connection_back` | **2 / 17** | ✓ |
| `test_merge_with_an_open_obligation_is_a_refused_envelope` | **2 / 17** | ✓ |

**Family size: 13** — and the coincidence with the brief's inherited 13 is exactly that. The
brief's 13 is `docs/ci/demo-suite-random-order.md` §3's count across **two** modules; only 9
of those are in `test_transitions.py`. This 13 is a different set, measured on a different
day, in a world that did not exist when the brief was written.

**The 13 decompose cleanly into 9 + 4, and the split is the whole finding:**

* the **9 that fail 17/17** are deterministic. They fail in isolation, in suite, shuffled,
  alone, concurrently, on an adopted database and on a freshly built one. Their messages name
  the cause in plain words — `{'error': 'demo_history_not_seeded', 'detail': 'mainline.defeater_option
  holds no row for check …'}` and `mainline_demo_api.retry.RetryBudgetExhausted` from a module
  that did not exist an hour earlier. **That is a red, not a flake.**
* the **4 that fail 2–4 of 17** failed **only in arm D**, the arm in which two pytest
  processes shared one scratch database. §4 is that experiment.

---

## 4 · The one non-deterministic signal, with a negative control that holds

Arms **D** and **E** are the same two pytest processes, launched at the same instant, on the
same file, in the same order, with the same flags, inside the same 40-second window and
therefore under the same source tree. **They differ in exactly one thing:** D's two processes
share one scratch database (`w_w4stab_shared`); E's two each have their own (`w_w4stab_e1`,
`w_w4stab_e2`). No `-k`, no `--deselect`, no marker, no environment difference other than
`MAINLINE_W4_DATABASE`.

The 9 deterministic world-2 failures are present in both arms and cancel. What does not
cancel:

**Signature: `psycopg.errors.SerializationFailure` (SQLSTATE `40001`, `RETRY_SERIALIZABLE`)
raised during SETUP** — that is `fresh_history`, i.e. `_seed_permit`'s thirteen-statement
transaction and its single unretried `commit()`.

| arm | runs | occurrences | distinct node ids |
|---|---:|---:|---:|
| **D — two processes, ONE shared scratch database** | 4 | **12** | **6** |
| **E — two processes, one database EACH** | 4 | **0** | **0** |
| every other arm in this document combined | 25 | **0** | **0** |

The six:

```
test_a_one_word_clearance_is_refused_by_the_api_not_the_gate        D1b, D2b
test_every_outcome_hands_the_connection_back                        D1a, D2a
test_materialise_checks_issues_a_receipt_and_moves_the_subject      D1a, D2a
test_merge_with_an_open_obligation_is_a_refused_envelope            D1a, D2a
test_sign_disposition_then_merge_commits                            D1b, D2b
test_the_request_after_a_sign_disposition_is_not_a_503              D1a, D2a
```

**All six take `fresh_history`.** Every one of the 12 occurrences is inside `_seed_permit`.
The two repetitions reproduced the same split — the process that lost the race is stable
because the two processes reach `_seed_permit` in the same relative order each time. Three of
the six are, node id for node id, the three that `qa/cluster-known-red.json`'s
`policy.the_NEW_of_2026_08_14_were_deliberately_not_added` recorded as erroring in SETUP with
this exact SQLSTATE, and that file was right to leave them NEW rather than file them.

**This is the mechanism, and it is not the one the inventory hypothesised.**
`qa/cluster-known-red.json` records, for one of the three `unstable` entries, *"a connection
left in a bad state by an earlier test"* — and is explicit that the mechanism was not proven.
The competitor measured here predicts a negative control, and the negative control holds:
close the cross-process channel and the signature disappears entirely, 12 → 0, in runs
started the same second. It also converges with two independent earlier studies
(`docs/ci/demo-suite-random-order.md` §5, `docs/ci/demo-suite-order.md` §5b) which reached the
same place from opposite directions.

**Cross-test contamination *within one process* is NOT-OBSERVED here.** The 16 sequential
runs of world 1 and the 9 sequential runs of world 2 give the same per-node-id verdict whether
the module ran alone, inside the full suite, or shuffled. That is a negative result, not a
proof of absence, and it is stated as one.

### 4.1 · Order was actually varied, and that is checkable from the XML

`pytest-random-order` 1.2.0 (declared and locked) was driven with
`--random-order --random-order-bucket=global` at seeds **4001, 4002, 4003** (module alone) and
**4101, 4102** (whole suite). The `<testcase>` elements appear in the XML in execution order,
so the shuffle is verifiable without trusting a log line. Checked that way: **all 5 randomised
runs differ from file order and none of the other 28 does**, and every run's node-id **set** is
identical. The full execution order of all five randomised runs is carried in the evidence file.

---

## 5 · THE RULING

> **R7 asked: justify 3, or widen the `unstable` list to the measured set. The answer is
> neither, and the reason is that `unstable` is a claim about a distribution over node ids
> while what was measured is a distribution over *conditions*.**

**5.1 — Do NOT widen the membership.** Widening to the measured family would put 13 node ids
into the inventory, of which **9 are deterministic failures caused by another lead's in-flight
source change**. Filing a deterministic red as `unstable` is precisely what
`qa/cluster-known-red.json`'s own `policy.what_this_file_may_never_become` forbids — *"a place
to put a test that started failing"* — and it would take nine tests off the seed lead's screen
on the day they appeared. The remaining 4 failed **only** in a two-process collision this
worker engineered on purpose; `cluster-tests.yml` runs one job, one container, one pytest, so
that condition cannot arise in the lane the inventory describes. Adding them would file a
local measurement hazard as a CI defect.

**5.2 — Do NOT call 3 "correct" either, and do NOT delete the three entries.** R7 is right
that three passes cannot refute a distribution, and this worker adds **25 more sequential
observations**, not a refutation. But the *stated reason* on those entries is now measurably
weaker than the alternative in §4, and two of the three (`test_suspending_a_merged_permit_commits`,
`test_the_request_after_a_sign_disposition_is_not_a_503`) sit inside the 11-member
`fresh_history` family while the third (`test_gate_run_is_reachable_through_handle_transition`)
does not — so even as a group of three they do not share one mechanism. **The honest edit is
to add the observations and re-ground the `reason`, not to move the membership in either
direction.**

**5.3 — The family that IS worth naming is structural, not statistical, and it has 11
members.** Every node id that takes `fresh_history` runs `_seed_permit`'s thirteen-statement
unretried transaction and is therefore exposed to `40001` the moment anything else writes the
same rows:

```
test_a_one_word_clearance_is_refused_by_the_api_not_the_gate
test_a_refused_merge_persists_nothing
test_an_undeclared_disposition_kind_is_422
test_every_outcome_hands_the_connection_back
test_materialise_checks_issues_a_receipt_and_moves_the_subject
test_merge_with_an_open_obligation_is_a_refused_envelope
test_merging_an_already_merged_permit_is_refused_by_the_epoch_pin
test_sign_disposition_hands_the_shared_connection_back_in_autocommit
test_sign_disposition_then_merge_commits
test_suspending_a_merged_permit_commits
test_the_request_after_a_sign_disposition_is_not_a_503
```

The corroboration is not circular. **Of the 11 node ids that any published reading in this
repository has ever recorded red in this module — the 3 `unstable`, the 3 NEW 40001s, the 9
from `demo-suite-random-order.md` §3, unioned — 9 take `fresh_history`. And of the 11 that
take `fresh_history`, 9 have been recorded red.** Two lists of eleven, built from completely
different evidence, agreeing on nine. The two published-red node ids outside the family
(`test_gate_run_is_reachable_through_handle_transition`,
`test_the_request_after_a_gate_run_is_not_a_503`) are both in the 17/17 deterministic group of
§3 and are explained there.

**5.4 — `cross_test_contamination` in `qa/cluster-known-red.json` is superseded, and this
worker rules on the disagreement it names.** That note says the contaminated set is *"at least
three node ids wide"* and *"does not include `test_the_request_after_a_gate_run_is_not_a_503`,
which this worker measured PASSING in all six of its runs."* Measured here: that node id fails
**17 of 17** world-2 runs and **1 of 16** world-1 runs. It is in the set. Both readings were
honest; they were taken in different worlds, and the note's error is not the count but the
absence of a stated condition. **A stability claim without the condition it was measured under
is not a measurement.** Whatever W3 records should carry the condition on its face.

---

## 6 · The counts, both ways, for W3

W3 owns `qa/cluster-known-red.json`. This worker does not edit it and has not. These are the
numbers to fold in; the machine-readable form is `handoff_to_w3` in the evidence file.

`unstable` entries as recorded: `runs_observed` 3, `runs_failed` 1, each, measured 2026-08-13
at `073dfea`. **Added by this worker** — the 25 SEQUENTIAL runs only, which are the ones
comparable to three consecutive whole-suite invocations; arms D and E are a deliberate
collision and its control, and folding them in would inflate `runs_observed` with runs that
were engineered rather than sampled:

| node id | recorded | + sequential (this worker) | **folded, sequential only** | folded, every arm |
|---|---|---|---|---|
| `test_gate_run_is_reachable_through_handle_transition` | 1/3 | 10/25 | **11 / 28** | 19 / 36 |
| `test_suspending_a_merged_permit_commits` | 1/3 | 9/25 | **10 / 28** | 18 / 36 |
| `test_the_request_after_a_sign_disposition_is_not_a_503` | 1/3 | 9/25 | **10 / 28** | 18 / 36 |

**Read the split before quoting the total.** Of each node id's 9–10 sequential failures,
**every one is in world 2** and **zero are in world 1** (except
`test_gate_run_is_reachable_through_handle_transition`, which has the single world-1 failure of
§3). Folded blindly these look like ~1-in-3 flakes; they are not. They are 0-in-16 in one world
(1-in-16 for the one exception) and 17-in-17 in the other.

**Recommended to W3, and it is a recommendation, not an edit:**

1. Raise `runs_observed` to **28** and `runs_failed` to **11 / 10 / 10** respectively, sequential
   arms only, citing this document and `evidence/qa/transitions-stability.json`.
2. Replace the `reason`/`evidence` prose with the measured mechanism (§4) and its negative
   control, keeping the superseded text per this repository's convention for superseded numbers.
3. Add the **condition** to each entry — the world it was observed in — because §5.4 is what
   happens when a distribution is recorded without one.
4. Do **not** add the 9 deterministic world-2 node ids anywhere in that file. They belong to
   the seed lead, they are failing right now for a named reason, and they are not unstable.
5. If a membership must be recorded, record the **11 `fresh_history` node ids of §5.3** as a
   *structurally exposed* family with the condition *"two runs of this suite sharing one scratch
   database"*, not as `unstable`.

---

## 7 · Reported, not repaired — R10 puts these out of this wave's scope

**Neither file below was edited by this worker, and neither moved during the battery.**
`test_transitions.py` carries mtime 2026-08-13T18:31:38 and sha256 `38dbfbbcd707a95b`;
`test_gate_run.py` carries mtime 2026-08-13T18:25:40 and sha256 `935c4e1782e8e6fc`. Both
mtimes predate every run in this document by fifteen hours, and both digests were re-read
from disk after the last run. The full record is in the evidence file's
`the_tree_moved_while_this_was_measured.watched_files_as_read_from_disk_after_the_battery`.

*Noted while writing this up, without claiming it:* `tests/concurrency/test_seed_permit_needs_retry.py`
and `packages/trappoint-testkit/src/trappoint_testkit/txn.py` appeared in the working tree
after the battery finished. Somebody is already acting on §7.1. This document is the
measurement, not the fix, and it does not assert what that work does.

### 7.1 · `_seed_permit` commits without a `40001` retry — `test_transitions.py:225`

**Owner:** the lead who owns `test_transitions.py`.

`_seed_permit` (lines 116–226) issues **thirteen** client statements — one `SELECT`, eight
`INSERT`s, and an `INSERT`+`UPDATE` pair twice round a loop — in one explicit transaction on a
connection opened `autocommit=False`, and ends at the bare `w4_conn.commit()` on **line 225**.
There is no retry, no `conn.transaction()` restart, and no bounded backoff. `db.py` already
carries `read()` with exactly that loop (`db.py:686-714`), and `transitions.py:49-52` rules —
correctly — that the POST path gets no retry because *"a helper that re-sent a merge because a
socket closed is a helper that can issue a permit twice."* **A fixture is not the POST path.**
Seeding a subject is idempotent in intent; it is the one place in this module where a retry is
both safe and missing.

*The brief's "roughly 29 statements" is worth one correction.* Thirteen statements are issued
by the fixture. The `seq=29` in the observed error is CockroachDB's transaction **sequence
number** at `COMMIT`, which counts what the triggers write as well (`check_materialised`,
`fn_permit_event_chain`, and whatever 0115 re-derives). The hazard is not smaller for that —
a transaction with 29 sequence numbers has a wider refresh span than one with 13 — but the
number should say what it is.

**Evidence:** §4. 12 occurrences, 6 distinct node ids, 4 runs. Reproducible on demand in about
forty seconds by starting two `pytest test_transitions.py` processes at the same instant with
the same `MAINLINE_W4_DATABASE`.

### 7.2 · The platform premise that a single node "never triggers" `40001` is measurably false

**Owner:** the same lead, plus whoever maintains `db.py`'s module docstring.

`verticals/mainline/apps/demo-api/src/mainline_demo_api/db.py:33` states:

> *"A single-node Docker cluster never produces `RETRY_SERIALIZABLE`."*

**Every run in this document was against one CockroachDB node on `127.0.0.1:26257`**, and that
node produced `RETRY_SERIALIZABLE` **12 times**, in SETUP, in four runs, with a negative
control that produced it zero times under the same load in the same window. `40001` is not a
Cloud-only concern and the retry loop is not Cloud-only work. The sentence is load-bearing —
it is the stated reason the POST path and the fixtures are off the retry path — so it should
be corrected to say what is actually true: a single node does not produce it *under a single
serialised writer*, and produces it readily the moment two writers touch the same rows. Which
is what CockroachDB Cloud will do with **one** writer.

### 7.3 · `SCRATCH_DB` is a fixed string — `test_gate_run.py:143`

**Owner:** the lead who owns `test_gate_run.py`.

```python
SCRATCH_DB = os.environ.get("MAINLINE_W4_DATABASE", "w_w4_api_transitions")
```

`test_transitions.py` imports `w4_database` from that module, so **two runs of this suite on
one host write the same rows of the same database by default.** In `cluster-tests.yml` this
cannot bite — one job, one container, one run — so it is a *local measurement* hazard. It has
already corrupted at least one published number: the three-run whole-suite measurement that
produced the `unstable` list was taken on a host running several workers' suites, and §4 shows
what that does.

**This worker used the existing escape hatch rather than editing the code.** Every run in
this document except BEFORE, AFTER and AFTER2 set `MAINLINE_W4_DATABASE` explicitly. Those
three deliberately did not, because the wave requires the lead's baseline command **verbatim**.
A `SHOW SESSIONS` sampled on the node during the battery found **four** sessions: this
worker's two, and two idle `mainline-demo-api` connections opened 2026-08-13T05:58:55Z and
05:59:15Z. That the host happened to be quiet is why those readings are usable at all — and
*"it happened to be quiet"* is not a property a measurement should have to depend on. One
sample is also not a guarantee, which is the point. A name carrying the process id, or the
fingerprint scheme `tests/conftest.py` already uses for the demo database, would end it.

---

## 8 · Full-suite `--crdb=reuse` — BEFORE and AFTER

```
.venv/Scripts/python.exe -m pytest verticals/mainline/apps/demo-api/tests \
  --crdb=reuse -q -p no:cacheprovider --junitxml=<report>
```

Read from `<testsuite>`, no `MAINLINE_W4_DATABASE` override — the lead's §1.1 command verbatim:

| | BEFORE (09:17:30) | AFTER (09:36:31) | AFTER2 (09:44:17) |
|---|---:|---:|---:|
| `tests` | **528** | **556** | **556** |
| `failures` | **1** | **21** | **21** |
| `errors` | **0** | **13** | **13** |
| `skipped` | **1** | **10** | **10** |
| executed | **527** | **546** | **546** |
| `time` | 53.109 s | 192.875 s | 67.471 s |

**AFTER2 was taken after both of this worker's files had been written**, which is what makes
it the strictly-after reading; AFTER was taken at the end of the battery. They are identical
in every count, which is the useful part: world 2 is *stable*, it is simply *red*. The 125-second
spread in `time` is host load — three of this worker's own processes and another lead's build
were on the machine during AFTER — and it is recorded rather than dropped because a wall time
is a measurement of the host, not of the suite.

**BEFORE reproduces the plan's §1.1 baseline exactly** — 528 / 527 executed / 1 skipped / 1
failed / 0 errors, the failure being
`test_reads.py::test_the_disposition_carries_the_lattice_and_the_projected_requirements` and
the skip being the `jsonschema` one.

**AFTER is nineteen minutes later and is not a statement about this worker's change.** This
worker wrote two files — this document and `evidence/qa/transitions-stability.json` — neither
of which pytest imports, collects or reads. Both live outside `testpaths`, neither is a
conftest, a fixture, a seed or a workflow, and the module under study is byte-identical
(sha256 `38dbfbbc…`) at BEFORE, at AFTER and at AFTER2. The delta is §2's timeline: the
collection grew 528 → 556 because `tests/test_defeaters.py` landed at 09:33:33, and the
failures and errors are another lead's in-flight `mainline.defeater_option` work, which was
**still being edited while AFTER ran**.

Two further readings of the same command are recorded in the evidence file (B01 at 09:20:45
and B03 at 09:22:20, with a private scratch database), and they bracket the change: **528 / 1
failed** and **528 / 2 failed**.

**One thing about AFTER's `10 skipped` must not be misread.** It is **not** the CI skip census
of `lane-honest-plan.md` R4, and not one of them is package-dependent. All ten are in the
brand-new `tests/test_defeaters.py`, all ten carry the same message —
*"112 of 271 migrations under …/db/migrations did not apply into `w2_defeaters_3b0aafc625f2`"* —
and they are that module's own scratch database failing to migrate while its author is still
writing it. A reader comparing AFTER's 10 against the ceiling of 1 would be comparing two
different tens.

---

## 9 · What would make this stronger

Stated so nobody reads §3's world-1 zero as more than it is:

* **World 1 is 16 runs over eight minutes**, 15 of them with zero red in this module. That is
  enough to say the three `unstable` node ids did not flake across three scopes and two orders
  in a quarter of an hour; it is not enough to put a rate on a defect that was seen once in
  three, and this document does not put one on it.
* **Nothing here ran against a multi-node cluster.** The `40001` measured in §4 was provoked by
  two processes on one node. CockroachDB Cloud will produce it with one, and no run in this
  repository has ever tested that.
* **World 2 is a moving target and this worker stopped measuring it deliberately.** Four files
  changed during the battery and a fifth was still changing when AFTER ran. Re-measuring the
  world-2 family after the seed lead's work lands is the obvious next reading, and until then
  its 9 should be read as *"deterministic under an in-flight tree"*, not as a stable count.
