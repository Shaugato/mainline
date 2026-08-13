<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# The demo-api suite's pass/skip split: what the hermetic lane does not run

**Worker:** W5, lane-controls wave (`docs/leads/lane-controls-plan.md`, ruling R7).
**Measured 2026-08-14 on TRAPPOINT**, against the working tree at
`D:/CoackroachDBxAWS/mainline` — HEAD `538193b` **plus uncommitted work** (50 modified, 30+
untracked paths) — with `.venv/Scripts/python.exe` and the pinned local node **CockroachDB
CCL v26.2.5** on `127.0.0.1:26257`.

Every number in this file was read from the `<testsuite>` attributes of a `--junitxml`
report written by the command printed beside it. Nothing here is copied from a terminal
scroll, from a recorded board, or from the lead's plan. The suite is I/O-bound and silent
for minutes under redirected stdout; two healthy runs have already been killed for looking
hung.

Five runs underlie this file: two hermetic (`--crdb=none`) and three cluster
(`--crdb=reuse`). Three cluster readings are reported rather than one because **the tree
was edited by other workers while it was being measured** — see §2.4, which turned out to
be the most useful measurement in the document.

---

## 1. The headline

> **The hermetic lane skips 202 of the demo-api suite's 528 tests — 38.3% of it — and
> exits 0.**

Not "fails quietly". Not "reports partial". `pytest` returns **exit status 0**, with **0
failures and 0 errors**, on a run in which more than a third of the suite never executed a
line. Every skip names its reason, which is the honest half; but an exit status is what a
dashboard reads, and on that channel a 38.3% hole and a clean suite are the same green tick.

**That number is the entire reason the cluster lane exists.**

---

## 2. The two commands, and the two results

Both invocations name the **same paths** and differ in exactly one flag.

### 2.1 Hermetic — no database

```
$ .venv/Scripts/python.exe -m pytest verticals/mainline/apps/demo-api/tests \
      --crdb=none -q -p no:cacheprovider --junitxml=before-hermetic.xml
```

### 2.2 Cluster — the real CockroachDB

```
$ .venv/Scripts/python.exe -m pytest verticals/mainline/apps/demo-api/tests \
      --crdb=reuse -q -p no:cacheprovider --junitxml=before-cluster.xml
```

### 2.3 The split

Hermetic reading 1 against cluster reading 1, the two taken back to back before the tree
moved. §2.4 carries the later readings; the **executed / skipped** rows below — the split
this document exists to publish — are identical in every one of them.

| measure | `--crdb=none` (hermetic) | `--crdb=reuse` (cluster) | delta |
|---|---:|---:|---:|
| collected | 528 | 528 | 0 |
| **executed** | **326** | **527** | **+201** |
| **skipped** | **202** | **1** | **−201** |
| passed | 326 | 460 | +134 |
| failed | 0 | 1 | +1 |
| errored | 0 | 66 | +66 |
| **pytest exit status** | **0** | **1** | — |
| wall time | 10.485 s | 58.679 s | +48.2 s |

**Collection is identical.** The 528 are collected either way — the skip is decided at
setup, not at collection, so no count of "tests in the suite" can reveal the hole. Only a
count of *executed* tests can, which is why `qa/cluster-known-red.json`'s floor is written
against `executed` and not against `tests`.

**38.3%** = 202 / 528. Put the other way: the hermetic lane exercises **61.7%** of the suite
and reports success for 100% of it.

### 2.4 The demonstration that arrived by accident: the tree moved mid-measurement

Between the two cluster readings above and the ones below, **another lead landed a 494-line
build-out of `verticals/mainline/db/seeds/demo/demo_world.sql`.** It was a large, real
change: it moved **57 tests from red to green** on the cluster side and took the suite from
66 errors to 0.

The hermetic lane was re-run across that change, same command, same paths:

| reading | collected | executed | skipped | failed | errored | exit | wall |
|---|---:|---:|---:|---:|---:|---:|---:|
| hermetic, before the seed change | 528 | 326 | 202 | 0 | 0 | **0** | 10.485 s |
| hermetic, after the seed change | 528 | 326 | 202 | 0 | 0 | **0** | 9.913 s |
| cluster, before | 528 | 527 | 1 | 1 | 66 | 1 | 58.679 s |
| cluster, after | 528 | 527 | 1 | 7 | 0 | 1 | 39.425 s |
| cluster, third reading | 528 | 527 | 1 | 12 | 0 | 1 | 139.913 s |

**The hermetic numbers are byte-for-byte identical either side of it.** Not similar —
identical, in all five columns. A 494-line change to the file the product deploys, one that
fixed 57 tests, was completely invisible to the lane that skips 202 of them. It could not
have reported the defect before, and it could not report the repair after.

This was not a designed experiment; the tree simply moved while it was being measured, and
the movement is recorded rather than smoothed away. It is the cleanest available statement
of what the 38.3% costs, and it is worth more than the percentage: **the hermetic lane is
not merely incomplete, it is insensitive to changes in the artefact the demo ships.**

The third cluster reading is included because it disagrees with the second, and the
disagreement is itself information: see §6 on what these numbers do and do not support. Its
five extra reds were traced to a stale locally-adopted database, not to the tree — the
seed's negative controls all pass at the current fingerprint. `qa/cluster-known-red.json`'s
`measured.re_measured` carries that investigation in full.

---

## 3. Where the hole is: seven modules go to zero

Executed counts per module, both lanes, from the same two XML documents.

| module | collected | hermetic executed | cluster executed | hermetic coverage |
|---|---:|---:|---:|---|
| `test_demo_guard_anonymous` | 13 | **0** | 13 | **none** |
| `test_gate_run` | 28 | **0** | 27 | **none** |
| `test_reads` | 75 | **0** | 75 | **none** |
| `test_refusal_row_factory` | 14 | **0** | 14 | **none** |
| `test_row_factory_contract` | 15 | **0** | 15 | **none** |
| `test_seed_covers_every_console_resource` | 14 | **0** | 14 | **none** |
| `test_transitions` | 33 | **0** | 33 | **none** |
| `test_credentials` | 17 | 7 | 17 | partial |
| `test_envelope` | 53 | 53 | 53 | full |
| `test_logbudget` | 39 | 39 | 39 | full |
| `test_ratelimit` | 73 | 73 | 73 | full |
| `test_response_contract` | 50 | 50 | 50 | full |
| `test_routes_gate_run` | 11 | 11 | 11 | full |
| `test_static_site` | 93 | 93 | 93 | full |
| **TOTAL** | **528** | **326** | **527** | — |

The shape matters more than the total. This is not 202 tests thinned evenly across the
suite — it is **seven entire modules reduced to zero executed tests**, plus 10 of 17 in an
eighth. A module at zero has no partial signal to degrade: it contributes nothing, and
nothing about the run says so except the skip count.

Two of those seven are worth naming individually.

* **`test_row_factory_contract` (15 tests, 0 executed hermetically.)**
  `docs/ci/test-collection.md` records what this module is: written specifically to catch a
  `dict_row`/`tuple_row` defect, carrying an explicit diagnosis naming
  `mainline_demo_api/refusal.py:235`. It was 627 lines when that document measured it and
  is **780 lines today** (`wc -l`, 2026-08-14) — the older figure is cited here only as the
  reading it was, which is the treatment this whole file argues for.
  `evidence/deploy/acceptance.json` records what shipped while the module was not running —
  `KeyError: 0` and the verdict `NOT PROVEN`, both confirmed present in that file today. It
  went unrun for one reason then (`testpaths` did not reach it) and it goes unrun for a
  second reason now. It is collected today. It still executes nothing without a database.
* **`test_seed_covers_every_console_resource` (14 tests, 0 executed hermetically.)**
  This is the module the suite-green lead names as the repository's tiebreaker for *which
  resources exist*. The check that decides whether the demo seed covers the console cannot
  run without the seed.

---

## 4. The skip is one mechanism, and it names itself

All **202** hermetic skips carry the same message, emitted by
`verticals/mainline/apps/demo-api/tests/conftest.py`'s `pytest_runtest_setup`:

> the session obtained no CockroachDB, so this cluster-backed test is skipped rather than
> allowed to reach a node the session declined to obtain. trappoint-testkit says: …

This is the good version of the defect. The skip is per-item, marker-driven
(`requires_cluster`), and states its reason, which is exactly the property `ci.yml`'s step
*"The suite, with every cluster test SKIPPED FOR A NAMED REASON"* claims. The conftest also
records why it exists: before it, two modules ignored `--crdb=none`, dialled
`127.0.0.1:26257` anyway, and killed a 9583-test run at 99% on the 120 s thread timeout.

**But a named reason is a property of the log, not of the exit status.** Nothing about
`pytest` exiting 0 distinguishes 202 named skips from 0 skips, and the log is not what a
dashboard, a badge, or a merge button reads.

### 4.1 One skip is not about the database, and it is the same one either way

The cluster lane's single skip is
`test_gate_run.py::test_payload_validates_against_the_json_schema` — *"jsonschema is not a
workspace dependency"*. It has nothing to do with CockroachDB, which is why
`qa/cluster-known-red.json` sets `floor.max_skipped` to **1** and not to 0.

Measured detail worth recording: **hermetically, that test is skipped for the *other*
reason.** `pytest_runtest_setup` fires before the test body, so the cluster-absence skip
masks the jsonschema skip, and the id appears among the 202. The jsonschema skip is
therefore invisible in the hermetic lane — a second, smaller instance of the same
phenomenon this whole document is about: a reason for not running is only legible in the
lane that got far enough to have it.

---

## 5. The floor refuses the hermetic run — measured, not asserted

`qa/cluster-known-red.json` carries `floor.min_executed = 440` and `floor.max_skipped = 1`
against exactly this failure mode. The claim is testable, so it was tested: the **green**
hermetic JUnit above was fed to the lane's own report as if it were a cluster run, with
pytest's real status of 0.

```
$ .venv/Scripts/python.exe scripts/ci/cluster_lane_report.py \
      --junit before-hermetic.xml --known qa/cluster-known-red.json --pytest-rc 0

cluster lane: 528 collected, 326 executed, 202 skipped, 0 failed, 0 errored

inventory: 64 known, 0 still failing, 0 now passing, 3 declared unstable, 0 NEW
::error title=the cluster lane proved nothing::only 326 of 528 demo-api tests EXECUTED;
  the floor is 440. …
::error title=the cluster lane skipped::202 test(s) skipped, ceiling 1. …
EXIT=1
```

**A run pytest calls green, refused, on both counts, with the numbers named.** This is the
one direction that matters: the floor is not decoration, and it does not need a red run to
fire. It also shows why both numbers are needed — `min_executed` alone would be satisfied
by a suite that grew, and `max_skipped` alone by a suite that shrank.

Neither number was touched by this worker. `min_executed` may only **rise** and
`max_skipped` may only **fall**; 326 < 440 is the measurement doing its job, not a floor
that needs adjusting to meet it.

---

## 6. What this does *not* say

* **This is not a claim about CI.** Both runs are local, on a dirty tree, against a
  long-lived local node. The hermetic run in GitHub Actions may skip a different number.
  What generalises is the *mechanism* — a marker-driven skip that leaves exit status
  unchanged — not the integer.
* **The cluster-side pass/fail composition is not stable, and this document does not
  pretend otherwise.** Three cluster readings in one sitting gave 1, 7 and 12 failures. The
  *split* — 528 collected, 527 executed, 1 skipped — was identical in all three, which is
  why the split is the number this file publishes and the failure count is not.
  `qa/cluster-known-red.json` already records that the failing set is measurably
  non-deterministic, which is why its inventory is a set-membership test and never an
  expected-count test.
* **A stale adopted database can make a control red for a defect that is already fixed —
  and that cuts both ways.** The third reading's five extra reds included two of the
  credential negative controls, asserting that the seed had been reshaped to match an
  application constant. That is the single most serious accusation in this repository, so it
  was chased down rather than reported: the seed diff contains no `signing_credential` or
  `credential_id` line, the current fingerprint's database enrols no derived credential, and
  all 17 tests in `test_credentials.py` pass at the current tree. The reds came from a
  database built under a different migration fingerprint and **adopted** rather than rebuilt.
  The hazard is that the adoption check asks only whether a database "already carries the
  seed", not whether it carries *this* seed — so the same path that produced a false red
  here could produce a false green if a poisoned seed landed while a clean database was
  adopted. That is a control finding for the lane-controls lead, not an inventory entry.
* **The hermetic 326 are not worthless.** They are 326 real tests and they pass. The claim
  is narrower and harder: the hermetic lane cannot see *any* defect in seven named modules,
  and its exit status does not admit that.
* **`--crdb=none` is honest on this box only because the conftest makes it so.** The
  conftest's own comment records that `test_gate_run.py:383` and
  `test_row_factory_contract.py:198` build their own DSN and fall back to a hardcoded
  `127.0.0.1:26257`; `ProcessGuard` blocks *spawning* a node, not connecting to one already
  listening. The 202-skip reading above is therefore a measurement of the marker discipline
  holding on a machine where a node **was** answering — which is the harder case, and the
  right one to have measured.
* **This document does not restate the repository-wide tally.** `ci.yml` carries that, with
  its superseded readings preserved. See §7.

---

## 7. Relation to `ci.yml`'s tally, which is a different number

`ci.yml` records the **repository-wide** marker tally, re-measured at `e944407`:

| reading | selected / deselected / total | status |
|---|---|---|
| `13 / 9240 / 9253` | 2026-08-10 | **superseded**, kept in place and labelled |
| `15 / 9824 / 9839` | 2026-08-13, HEAD `073dfea` | current |
| `15 / 9884 / 9899` | same sitting, three hours later | current |

That tally counts *declared reds* across the whole repository. It is not this document's
subject and the two must not be conflated: the demo-api suite's 528 are a subset of those
totals, and its 202-test hermetic hole is invisible in every one of those six numbers.

Both `ci.yml` readings are kept, with the older pair explicitly marked superseded. That
treatment is correct and this document follows it: §2.3's numbers carry the date, the tree
state and the command, so that the next person to measure supersedes them rather than
silently overwrites them.

---

## 8. Reproducing this

```
# hermetic
.venv/Scripts/python.exe -m pytest verticals/mainline/apps/demo-api/tests \
    --crdb=none -q -p no:cacheprovider --junitxml=hermetic.xml

# cluster (requires CockroachDB v26.2.5 on 127.0.0.1:26257)
.venv/Scripts/python.exe -m pytest verticals/mainline/apps/demo-api/tests \
    --crdb=reuse -q -p no:cacheprovider --junitxml=cluster.xml

# the split, from the XML and only from the XML
.venv/Scripts/python.exe - <<'PY'
import xml.etree.ElementTree as ET
for label, path in (("hermetic", "hermetic.xml"), ("cluster", "cluster.xml")):
    root = ET.parse(path).getroot()
    s = root if root.tag == "testsuite" else root.find("testsuite")
    t, sk = int(s.get("tests")), int(s.get("skipped"))
    print(f"{label:9s} collected={t} executed={t - sk} skipped={sk} "
          f"failures={s.get('failures')} errors={s.get('errors')}")
PY

# the floor, exercised against the green hermetic run
.venv/Scripts/python.exe scripts/ci/cluster_lane_report.py \
    --junit hermetic.xml --known qa/cluster-known-red.json --pytest-rc 0
```
