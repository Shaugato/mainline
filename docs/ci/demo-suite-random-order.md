<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: Apache-2.0
-->

# Randomised order, actually run — and what seventeen runs say

**Worker:** W6. **Date:** 2026-08-14. **Host:** TRAPPOINT, CockroachDB CCL v26.2.5 on
`127.0.0.1:26257`. **HEAD:** `e944407`, working tree dirty and *moving* — see §6.
**Numbers read from `--junitxml` root elements and from nowhere else.**

---

## 0 · The one-paragraph answer

Randomised order has now been run: **15 randomised full-suite invocations across 8
seed/bucket combinations**, plus 2 default-order runs. It surfaced **13 distinct node ids**
in `test_transitions.py` and `test_gate_run.py` that the default order did not surface in
the same window — including the two node ids the wave brief and `qa/cluster-known-red.json`
respectively argued about. **But the order is not the variable.** The same seed, run twice
against the same tree, produced 0 failures and then 5. What *is* the variable, demonstrated
with a negative control that behaves exactly as the hypothesis predicts, is that
`test_gate_run.py:143` names its scratch database with a **fixed string** — so two
simultaneous runs of this suite on one host write the same rows and collide on `40001`.

So the honest verdict is: **cross-test contamination inside one process, caused by test
order, is NOT-OBSERVED in my runs — and now for a stated reason rather than for want of an
instrument.** A different contamination, *between* processes, is **observed, reproduced and
diagnosed**, and it is a sufficient explanation for the `unstable` entries this repository
has been carrying. §5 says who owns it. An earlier study (§5b) independently found, fixed
and A/B-tested one genuine intra-process order defect, and — without naming it as such —
ran its clean battery with the cross-process channel already closed; the two measurements
converge, which is why §5's finding is stated as a default that is wrong rather than as a
laptop quirk.

---

## 1 · What was installed, and why that one

`pip list` on 2026-08-14: pytest 9.1.1, pytest-timeout 2.4.0, and no shuffler of any kind.
Every green this repository has reported was a green **in one order**, and two runs in the
same order cannot separate *"the contamination is fixed"* from *"this order does not
trigger it"*.

Installed: **`pytest-random-order` 1.2.0**, declared in `pyproject.toml`'s `dev` group with
the argument written out beside it, and locked (`uv lock` added exactly 15 lines:
one manifest edge and one package block; lockfile `revision` unchanged, `uv lock --check`
green).

**Not `pytest-randomly`**, although two workflows here already pass `-p no:randomly`. That
default — on for every suite the moment it is installed — is the reason:

* it would shuffle all 9,324 collected tests across eighteen workflows in the same commit
  that was meant to measure one suite; and
* it reseeds `random`/`numpy.random` before every test, and sixteen modules here drive
  Hypothesis. A run that changes both the ORDER and the DATA cannot attribute a new failure
  to either, and attribution is the entire point.

`pytest-random-order` is inert until asked. **Verified rather than assumed:** two default
`--collect-only` runs of the demo-api suite, one with the plugin and one with
`-p no:random_order`, produced **byte-identical** 525-line collections. So the before/after
comparison in §3 is a comparison, not an artefact of installing an instrument.

Consequence stated rather than left as a trap: the two `-p no:randomly` guards
(`schema.yml:485`, `nightly-differential.yml:182,343`) remain **inert**, because the plugin
they name is still not installed. `-p no:<absent plugin>` is a no-op, so they are harmless —
but they are not doing the job their comments describe. That belongs to whoever owns those
workflows.

## 2 · How to run it

```
.venv/Scripts/python.exe -m pytest verticals/mainline/apps/demo-api/tests \
    --crdb=reuse -q -p no:cacheprovider \
    --random-order --random-order-bucket=global --random-order-seed=<N> \
    --junit-xml=<report>.xml
```

`--random-order-bucket` is the control that matters and it is why this plugin was chosen:
`module` keeps each module's tests together and shuffles the modules, `global` interleaves
tests from different modules freely. That is the difference between *"two tests in one
module interfere"* and *"two modules interfere"*, and only the second is what a warm Lambda
reusing one connection would look like.

## 3 · Every run, with its seed and its numbers

`w4` counts failing node ids in `test_transitions.py` + `test_gate_run.py` — the only
modules where anything moved. All figures from the JUnit root element.

| run | seed | bucket | tests | passed | failed | errors | skipped | w4 |
|---|---:|---|---:|---:|---:|---:|---:|---:|
| **BEFORE** (default order) | – | default | 524 | 441 | 6 | 63 | 14 | **0** |
| rand | 101 | global | 524 | 454 | 6 | 63 | 1 | **0** |
| rand | 202 | global | 524 | 451 | 8 | 64 | 1 | **3** |
| rand | 303 | global | 524 | 452 | 6 | 65 | 1 | **2** |
| rand | 404 | module | 524 | 454 | 6 | 63 | 1 | **0** |
| rand | 505 | module | 524 | 454 | 6 | 63 | 1 | **0** |
| rand | 606 | global | 524 | 453 | 6 | 64 | 1 | **2** |
| repeat a | 202 | global | 524 | 411 | 7 | 1 | 105 | **1** |
| repeat a | 101 | global | 525 | 458 | 0 | 66 | 1 | **3** |
| repeat b | 202 | global | 525 | 455 | 4 | 65 | 1 | **6** |
| repeat b | 101 | global | 525 | 420 | 0 | 0 | 105 | **0** |
| repeat c | 202 | global | 528 | 462 | 0 | 65 | 1 | **2** |
| repeat c | 101 | global | 528 | 459 | 4 | 64 | 1 | **5** |
| shared-db | 202 | global | 528 | 464 | 0 | 63 | 1 | **0** |
| own-db | 202 | global | 528 | 462 | 2 | 63 | 1 | **0** |
| own-db | 101 | global | 528 | 464 | 0 | 63 | 1 | **0** |
| **AFTER** (default order) | – | default | 528 | 464 | **0** | 63 | 1 | **0** |

The first six randomised runs (seeds 101–505) all ran against **one** `git status`
fingerprint, `f2a975ce8ff5b230`, back to back between 02:58 and 03:02.

**The thirteen node ids that failed in at least one randomised run** (count of the 17 runs
each was seen failing in):

```
 3  test_transitions::test_every_outcome_hands_the_connection_back
 2  test_transitions::test_sign_disposition_hands_the_shared_connection_back_in_autocommit
 2  test_transitions::test_materialise_checks_issues_a_receipt_and_moves_the_subject
 2  test_transitions::test_the_request_after_a_gate_run_is_not_a_503
 2  test_transitions::test_a_refused_merge_persists_nothing
 2  test_transitions::test_sign_disposition_then_merge_commits
 2  test_transitions::test_merge_with_an_open_obligation_is_a_refused_envelope
 2  test_gate_run::test_two_consecutive_runs_see_the_same_subject
 2  test_gate_run::test_gate_run_verdict_is_proven
 2  test_gate_run::test_the_payload_proves_its_own_persistence_claim
 1  test_transitions::test_an_undeclared_disposition_kind_is_422
 1  test_transitions::test_gate_run_is_reachable_through_handle_transition
 1  test_gate_run::test_concurrent_runs_do_not_collide
```

Two of these matter for what this repository already believed:

* **`test_the_request_after_a_gate_run_is_not_a_503`** is the node id the wave brief named
  as contaminated and which `qa/cluster-known-red.json` recorded as **passing in all six
  runs it was observed over**. It fails here. That file's conclusion — *"the contaminated
  set is at least three node ids wide and does not include that one"* — is superseded: the
  set is at least **thirteen** wide and does include it.
* Of the three node ids that file declares `unstable`, **only one**
  (`test_gate_run_is_reachable_through_handle_transition`) failed in any of my seventeen
  runs, and only once. The `unstable` list is not wrong, but it is aimed at three members
  of a much larger family.

**`qa/cluster-known-red.json` is byte-identical** (sha256
`b8079df5c33e9b7fc40698b3906ffe01f6877a43c5f9097401d7cdfc2f203945`, mtime 2026-08-13
21:05). Nothing above was written into it. Its `groups` list is a ceiling expected to be
deleted, and it is the cluster lane's file, not mine.

## 4 · The reading I first took, and the control that overturned it

The first six runs read cleanly: three `global` seeds gave 0, 3 and 2 extra failures and two
`module` seeds gave 0 and 0, which says *contamination requires tests from different
modules to interleave*. It is a tidy story and it is not supported.

**The control that broke it.** Seeds 202 and 101 were each re-run at the same tree
fingerprint, minutes apart, in the same order they had run before:

| seed | tree | first run | second run |
|---:|---|---:|---:|
| 101 | `76f28008f8cc0321` | **0** w4 failures | **5** w4 failures |
| 202 | `76f28008f8cc0321` | **6** w4 failures | **2** w4 failures |

**The same seed produces the same order. Different outcomes from the same order mean the
order is not what is deciding.** Whatever moved, moved between the runs and not inside
them.

(The fingerprint is a hash of `git status --porcelain`, which records *which* paths are
modified and not *what is in them* — so a worker editing an already-modified file leaves it
unchanged. That weakens "same tree" and I am not leaning on it. §5's experiment does not
depend on it at all.)

## 5 · What IS happening, reproduced with a negative control

`test_gate_run.py:143`:

```python
SCRATCH_DB = os.environ.get("MAINLINE_W4_DATABASE", "w_w4_api_transitions")
```

A **fixed** name. `test_transitions.py` imports `w4_database` from that module, so every
simultaneous run of this suite on one host — and this host was running five workers'
suites — reads and writes the same rows of the same database. Five concurrent sessions
were observed on the node during the measurement window.

**The experiment.** Two runs of `test_transitions.py` alone, started simultaneously, in the
**default order**, with no shuffler involved. Arm A shares the default database. Arm B gives
each run a scratch database of its own via `MAINLINE_W4_DATABASE`. Everything else — tree,
order, second — is identical; the only variable is whether they share a database.

| | arm A (shared `w_w4_api_transitions`) | arm B (one database each) |
|---|---|---|
| repetition 1 | **A1 error, A2 error** | B1 clean, B2 clean |
| repetition 2 | **A1 failure**, A2 clean | B1 clean, B2 clean |
| total | **3 of 4 runs red** | **0 of 4 runs red** |

The node ids arm A produced:

```
rep 1  ERROR  test_sign_disposition_hands_the_shared_connection_back_in_autocommit   (40001)
rep 1  ERROR  test_the_request_after_a_sign_disposition_is_not_a_503                 (40001)
rep 2  FAIL   test_the_request_after_a_gate_run_is_not_a_503
```

The second of those is **one of the three node ids `qa/cluster-known-red.json` declares
`unstable`**. The third is **the node id the wave brief named**. The experiment reproduces
both, on demand, in about forty seconds, with a negative control that stays green.

**The mechanism, end to end.** The errors are raised at `test_transitions.py:224`, inside
`_seed_permit`, on `w4_conn.commit()`, with the connection already in psycopg's `[BAD]`
state:

```
psycopg.errors.SerializationFailure: restart transaction:
TransactionRetryWithProtoRefreshError: TransactionRetryError:
retry txn (RETRY_SERIALIZABLE - failed preemptive refresh) … seq=29 … stat=PENDING
```

`_seed_permit` issues ~29 statements in one explicit transaction and commits. A concurrent
run writing the same permit rows pushes its read timestamp, the refresh fails, and the
COMMIT takes `40001`. **The fixture has no retry loop**, so the collision surfaces as an
ERROR in setup rather than as a retry — which is why these show up as errors and why they
move around.

**Two things this is NOT, checked rather than assumed:**

* It is **not** the hypothesis `qa/cluster-known-red.json` records (*"a connection left in a
  bad state by an earlier test"*). That file is explicit that the mechanism was not proven,
  and this is a better-supported competitor: it predicts a negative control and the negative
  control holds.
* It is **not** a product defect on the transition path. `transitions.py:45-51` rules that
  `40001` there is surfaced as `503 retry` and never retried, because a transition is not
  idempotent and *"a helper that re-sent a merge because a socket closed is a helper that can
  issue a permit twice."* The `503 database_unreachable` that
  `test_materialise_checks_issues_a_receipt_and_moves_the_subject` saw is the product doing
  exactly what it says it does under a genuine serialization conflict. I checked this before
  writing it up, and it is the reason no defect is claimed there.

### Reported, not repaired — none of these are in W6's owned paths

1. **`test_gate_run.py:143` gives its scratch database a fixed name.** Two runs on one host
   collide. In `cluster-tests.yml` this cannot bite — one job, one container, one run — so
   it is a *local measurement* hazard, and it has been corrupting local measurements,
   including the three-run measurement that produced the `unstable` list. A name that
   included the process id, or the fingerprint scheme the demo database already uses, would
   end it. **Owner: whoever owns `test_gate_run.py`.** Reproduction: the table above; the
   driver is `contention.sh` in W6's scratch directory and is four lines of `pytest`.
2. **`_seed_permit` (`test_transitions.py:224`) commits without a `40001` retry.** On a
   single-node local cluster this is only reachable under concurrency. On CockroachDB Cloud
   — a managed multi-node cluster, which is where this demo deploys and which the platform
   note says *needs* a retry loop — a fixture that cannot survive one `40001` is a fixture
   that will flake in the environment that matters. **Owner: whoever owns
   `test_transitions.py`.** `db.py` already has `_with_retry`; this fixture is off that path
   by design and would need its own.
3. **The `unstable` list in `qa/cluster-known-red.json` is aimed at three of thirteen.** Not
   an edit for this wave — the plan rules the file is the cluster lane's and its groups are
   to be deleted, not amended — but whoever deletes it should know the family is larger and
   that §5 offers a cause. **Owner: the cluster lane.**

## 5b · An earlier study reached the same place from the other side

`docs/ci/demo-suite-order.md` (a worker of the 2026-08-13 wave, harness
`scripts/qa/demo_suite_order.py`) is not a competing document and should be read beside
this one. I found it after taking my measurements, which makes the agreement worth
something.

It reports two things that bear directly on the verdict here:

* **An intra-process order defect existed, was reproduced, and was FIXED.** Two
  session-scoped fixtures (`w4_database` in `test_gate_run.py`, `w1_database` in
  `test_row_factory_contract.py`) both published the same four DSN environment variables
  for two different databases, so an interleaved order handed a test the wrong one. Its
  A/B — the same file swapped between `git show HEAD:…` and the repaired version, three
  seeds, across three different worlds — produced six order-induced failures in **every**
  seeded run of the old file and **zero** in every seeded run of the new one. That is the
  cross-test contamination this repository was looking for, and it is gone. My runs are
  after that fix, which is consistent with my never having seen its signature.
* **Its five-seed battery ran with private scratch databases** — `MAINLINE_W1_DATABASE`
  and `MAINLINE_W4_DATABASE` both set — and reported every seed *identical to file order,
  test for test*.

That second point is the convergence. **That study closed the cross-process channel §5
identifies, without naming it as the reason, and saw a clean result. I left it open and saw
failures that disappear the moment it is closed.** Two independent measurements, from
opposite directions, agreeing on where the residual noise comes from — and it makes finding
1 of §5 stronger, not weaker: the workaround is already being applied by hand, in a
document, by a worker who had to discover it. A fixed database name that everyone has
learned to override with an environment variable is a default that is wrong.

One disagreement, stated plainly. That document declines to add a pytest plugin, on the
grounds that `uv lock --check` in `ci.yml` is what makes *"a stranger resolves the same
dependency graph"* true and that a shuffle is only `random.Random(seed)`. The concern is
right and it is answered by measurement rather than waved away: the lock was regenerated
with `uv lock`, the diff is **15 lines and purely additive** (one manifest edge, one package
block), the lockfile `revision` did not move, and `uv lock --check` is green. What the
plugin buys over a home-grown shuffler is the thing §4 turned on — `--random-order-bucket`,
which separates *modules interleaving* from *tests within a module interleaving* — and a
declaration CI can install, which an `out/order/*.args` file on one laptop is not.

## 6 · Why "fixed" is not available, and what would make it available

The measurement window was not quiet. Five workers were editing one working tree and
running suites against one CockroachDB node throughout. Sampling the *content* of
`verticals/mainline/apps/demo-api/{src,tests}` and `db/seeds/demo` every twenty seconds, the
hash changed **seven times in five minutes**. The suite grew 524 → 528 tests mid-measurement.
Two runs recorded 105 skips because a neighbour's scratch database was half-built at that
moment.

So:

* **PROVEN** — the instrument exists, is declared, is locked, is inert by default, and has
  been run 15 times across 8 seed/bucket combinations with every seed recorded.
* **PROVEN** — the failing set of `test_transitions.py` / `test_gate_run.py` is
  non-deterministic *independently of test order*, and concurrent use of one fixed-name
  scratch database is a sufficient cause, demonstrated with a negative control.
* **NOT-OBSERVED, and NOT claimable as fixed from my evidence** — cross-test contamination
  *within a single process, caused by the order tests run in*. None of my runs isolated it,
  and **none of them could have**: the cross-process channel was open the whole time, so it
  can mask an intra-process effect and can mimic one. A single green randomised run at one
  seed would have proved very little on a quiet host; on this host it proves less.
  §5b's study *does* carry a fixed-and-demonstrated intra-process defect with a proper A/B,
  and that finding stands on its own evidence — but it is that worker's measurement, not
  mine, and I am not relabelling it with my runs.

**What would settle it**, and it is cheap: close the cross-process channel first (finding 1
above), then run three seeds at `--random-order-bucket=global` and three at `module` on a
host with **one** worker on it. Until then the correct sentence is *not-observed*, and
writing *fixed* would be the shortcut this wave exists to refuse.

## 7 · Before / after, and the regression set

Full-suite `--crdb=reuse`, default order, JUnit root elements:

| | tests | passed | failed | errors | skipped | wall |
|---|---:|---:|---:|---:|---:|---:|
| **BEFORE** (02:55) | 524 | 441 | 6 | 63 | 14 | 102.7 s |
| **AFTER** (04:0x) | 528 | **464** | **0** | 63 | 1 | 42.0 s |

**Regression set — node ids failing in AFTER but not in BEFORE: EMPTY.** Six node ids went
the other way (five owned by W1/W2/W4, one by W3); the 63 errors are unchanged and are
blocker 1, which is not mine. Neither figure is a claim about W6's work alone — five workers
were landing changes into this tree between the two runs. What the diff does establish is
that **nothing W6 changed broke a neighbour**, which is the question the before/after is
there to answer.

The 14 → 1 skip change is not W6's either: thirteen of the fourteen were
`test_row_factory_contract` reporting *"98 of 271 migrations did not apply into
`w_w1_rowfactory`"*, and a neighbour rebuilt that database. It is worth recording because
**14 skips would have failed the cluster lane's floor** (`max_skipped: 1`) for a reason that
has nothing to do with the cluster being absent — see
`docs/ci/cluster-lane-report-controls.md` §6(b).

`tests/ci/` after: **22 passed, 2 failed** — both failures are
`test_demo_seed_is_frozen::test_the_deployed_seed_files_have_not_changed`, owed a
re-baseline by whoever changed the seed bytes (W1 and W3, in this wave). That test's own
docstring says a red there is a question, not a verdict, and answering it is not W6's.
All 21 controls in `tests/ci/test_cluster_lane_report.py` pass.
