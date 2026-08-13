<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# The cluster lane's 2×2, measured — with the artefacts attached

**Worker:** W4, lane-controls wave. **Measured 2026-08-14 on TRAPPOINT**, working tree
`D:/CoackroachDBxAWS/mainline` at HEAD `538193b`, `.venv/Scripts/python.exe` (pytest 9.1.1),
against the local **CockroachDB CCL v26.2.5** on `127.0.0.1:26257`.

**Every number in this document was read out of a `--junitxml` file that is committed beside
it**, under `evidence/ci/cluster-lane-2x2/`. None was read off a terminal scroll. That is not
a stylistic preference: this suite is I/O-bound and prints nothing for minutes at a time, and
two healthy runs have already been killed by leads who believed they had hung.

The machine-readable form of everything below is
[`evidence/ci/cluster-lane-2x2/summary.json`](../../evidence/ci/cluster-lane-2x2/summary.json),
generated from the XML rather than typed in.

---

## 0. Why this document was rewritten

The previous revision of this file (2026-08-13) reported the same 2×2 as measured. It was
prose only — **no JUnit file, no artefact, nothing a reader could recount.** In the meantime
`.github/workflows/cluster-lane-bites.yml` was found never to have executed at all: it did
not parse, so its only run created zero jobs and lasted 0 s. The lane's central claim had
therefore produced zero evidence in the project's history.

This revision replaces the unbacked readings with measurements that ship their inputs. The
2026-08-13 readings are preserved in §8 rather than deleted, because the convention in this
repository is that a superseded measurement stays visible next to the one that replaced it.

**The headline is not the same as last time.** Cell 3 came back exactly as the lane predicts,
and more strongly than the lane asserts. Cell 4 came back red **twice, for different reasons**,
and on the first attempt it was red in a way the workflow's own assertion would have — and
should have — refused to accept as a proof.

---

## 1. What ran

The subset is the one `cluster-lane-bites.yml` names in `SUBSET`, run with the same argv
modulo `--crdb`:

```
SUB="verticals/mainline/apps/demo-api/tests/test_credentials.py
     verticals/mainline/apps/demo-api/tests/test_gate_run.py
     verticals/mainline/apps/demo-api/tests/test_transitions.py"

.venv/Scripts/python.exe -m pytest $SUB --crdb=<none|reuse> -q -p no:cacheprovider \
    --junitxml=evidence/ci/cluster-lane-2x2/<file>.xml
```

78 tests collect in every cell, in every attempt. The order was the one the brief fixes:
cell 1, cell 2, `--plant seed-credential-swap`, cell 3, cell 4, `--revert`.

---

## 2. The 2×2 as measured

Every row is `collected / executed / skipped / failures / errors / passed`, with `executed`
defined as `collected − skipped`, exactly as the workflow computes it.

| cell | plant | `--crdb` | artefact | collected | executed | skipped | fail | err | passed | rc | wall |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **1** attempt 1 | absent | `reuse` | `junit-absent-cluster.xml` | 78 | 77 | 1 | 0 | **1** | 76 | **1** | 19.67 s |
| **1** attempt 2 | absent | `reuse` | `junit-absent-cluster-attempt2.xml` | 78 | 77 | 1 | 0 | 0 | **77** | 0 | 18.71 s |
| **1** attempt 3 | absent | `reuse` | `junit-absent-cluster-attempt3.xml` | 78 | 77 | 1 | 0 | 0 | **77** | 0 | 19.51 s |
| **1** attempt 4 | absent | `reuse` | `junit-absent-cluster-attempt4.xml` | 78 | 77 | 1 | 0 | 0 | **77** | 0 | 18.60 s |
| **2** | absent | `none` | `junit-absent-hermetic.xml` | 78 | **7** | 71 | 0 | 0 | **7** | 0 | 0.27 s |
| **3** | present | `none` | `junit-planted-hermetic.xml` | 78 | **7** | 71 | 0 | 0 | **7** | 0 | 0.26 s |
| **4** attempt 1 | present | `reuse` | `junit-planted-cluster.xml` | 78 | 67 | **11** | 2 | 2 | 63 | **1** | 121.92 s |
| **4** attempt 2 | present | `reuse` | `junit-planted-cluster-attempt2.xml` | 78 | 70 | **8** | **1** | 0 | 69 | **1** | 145.52 s |

Reduced to the shape the lane argues about:

|  | plant ABSENT | plant PRESENT |
|---|---|---|
| `--crdb=none`  | GREEN — 7 executed, 7 passed, 71 skipped | **GREEN — 7 executed, 7 passed, 71 skipped** |
| `--crdb=reuse` | GREEN — 77 executed, 77 passed (3 of 4 attempts) | **RED — and the test the plant names is what failed (attempt 2)** |

---

## 3. Cell 2 versus cell 3 — the comparison the whole wave turns on

This is the assertion the workflow makes (`executed != before` → fail), and it is the one the
brief singled out. Measured, from the two XML files:

```
cell 2 (plant ABSENT, --crdb=none):  executed = 7
cell 3 (plant PRESENT, --crdb=none): executed = 7
```

**VERDICT: the counts are EQUAL. The assertion holds, and the cell-3 equality must not be
relaxed — there was no pressure to relax it.**

The measurement is stronger than the assertion. The workflow compares two integers; this
worker compared the two **sets of executed node ids**, and they are identical — the same
seven tests by name, all seven passing, in both trees:

```
test_credentials.py::test_every_seed_file_this_suite_names_exists
test_credentials.py::test_gate_run_resolves_the_credentials_it_binds
test_credentials.py::test_no_module_derives_a_credential_id
test_credentials.py::test_the_credentials_are_resolved_before_the_beats_transaction_opens
test_credentials.py::test_the_migrations_directory_this_suite_builds_from_is_present
test_credentials.py::test_the_resolver_reads_the_table_its_refusals_name
test_credentials.py::test_the_seed_files_this_suite_runs_against_are_the_ones_the_deploy_applies
```

`summary.json` records this as `executed_nodeid_sets_identical: true`. A count equality could
in principle be satisfied by one test dropping out and another appearing; the set equality
cannot.

Two of those seven are worth naming, because they are the reason the claim is not trivial.
`test_no_module_derives_a_credential_id` is the AST ratchet — it walks the package for a
derived credential id and passes, because the planted derivation is in a **seed**, not in
code. `test_the_seed_files_this_suite_runs_against_are_the_ones_the_deploy_applies` compares
the deploy's `SEED_FILES` **list** against the suite's, and passes, because the file names did
not change — only the bytes inside one of them did. Two hermetic controls whose names sound
like they should have caught this ran, and could not. That is the sentence the cluster lane
exists to earn.

---

## 4. Cell 4 — red twice, and only once was it a proof

The workflow does not accept "pytest exited non-zero" as a falsifiability proof. It reads the
JUnit and requires that the test the plant's own manifest declares in `caught_by` —

```
verticals/mainline/apps/demo-api/tests/test_credentials.py
    ::test_the_deployed_seed_does_not_enrol_the_value_gate_run_used_to_derive
```

— is among the failures. Both attempts were red. They are not the same result.

### Attempt 2 — the clean proof

**1 failed, 69 passed, 8 skipped; the single failure is exactly `caught_by`, and nothing
else failed or errored.**

```
FAILED test_credentials.py::test_the_deployed_seed_does_not_enrol_the_value_gate_run_used_to_derive
```

The red is unambiguous by construction: there is no other failure it could be attributed to.
The workflow's `caught_by` assertion passes on this run.

### Attempt 1 — red, but the workflow would have refused it, correctly

**2 failed, 2 errored, 11 skipped — and `caught_by` was SKIPPED, not failed.**

| node id | outcome | caused by the plant? |
|---|---|---|
| `test_gate_run.py::test_the_admission_is_a_green_this_database_could_have_refused` | FAIL | **yes** — its own message is *"the deployed seed enrols the value gate_run used to DERIVE, so the divergence this control exists to exhibit does not exist in this database"* |
| `test_gate_run.py::test_the_deployed_seed_and_the_proof_seed_are_two_different_worlds` | FAIL | **yes** — *"the DEPLOYED seed enrols the derived credential id"*, `assert 1 == 0` |
| `test_transitions.py::test_sign_disposition_then_merge_commits` | ERROR | **no** — `40001 RETRY_SERIALIZABLE` on setup, see §5 finding 1 |
| `test_transitions.py::test_materialise_checks_issues_a_receipt_and_moves_the_subject` | ERROR | **no** — same `40001`, same fixture |
| `test_credentials.py::…_used_to_derive` **(`caught_by`)** | **SKIPPED** | n/a — its database did not build, see §5 finding 2 |

So on attempt 1 the lane would have printed *"the cluster lane went red for the wrong
reason"* and exited 1. **That is the design working.** A red cell that is red for an
unrelated reason is not a falsifiability proof, and the lane says so rather than banking it.

**The `caught_by` check is doing real work and must not be relaxed to "non-zero is enough".**
Attempt 1 is the concrete counter-example: a run that was red, that contained two genuine
plant-caused failures, and in which the named control never executed at all. "Non-zero is
enough" would have called that a proof.

---

## 5. Findings

Five things this measurement establishes that were not known before it. None of them is
repaired here — every one lives in a file another worker owns, and the rule that outranks
this document says a fixture you believe is wrong gets reported with evidence and left alone.

### Finding 1 — the subset's cluster cells carry an unretried `40001`, and it is the same defect twice

Cell 1 attempt 1 and both cell-4-attempt-1 errors are the **same** failure:

```
psycopg.errors.SerializationFailure: restart transaction:
  TransactionRetryError: retry txn (RETRY_SERIALIZABLE - failed preemptive refresh)
raised at  test_transitions.py:225  in  _seed_permit  ->  w4_conn.commit()
```

`test_transitions.py::_seed_permit` ends in a bare `w4_conn.commit()` with **no retry loop**.
`conftest._apply_seeds` deliberately calls the deployer's own `Applier`, *"whose loop retries
`40001` with backoff"*; this fixture has no such loop. The platform constraint for this
project names a `40001 RETRY_SERIALIZABLE` retry loop as required, and records that
single-node local Docker rarely triggers it — it triggered here, on a single local node,
**twice in eight subset runs**.

Measured rate in this sitting: **cell 1 was red on 1 of 4 attempts (77 executed each time,
76 passed once, 77 passed three times).**

Consequence for the lane, which W1 should know: cell 1 runs under `set -euo pipefail`, so a
red pytest aborts the step and the whole 2×2 stops before the plant is applied. That is the
correct behaviour — the lane refuses to measure against a dirty specimen — but it means the
bites lane will intermittently abort at cell 1 for a reason that has nothing to do with the
plant, and the answer is a retry loop in `_seed_permit`, **never a relaxed cell 1.**

*Owner: whoever owns `verticals/mainline/apps/demo-api/tests/test_transitions.py`. Not W4.*

### Finding 2 — the plant forces two fresh database builds, and one of the two partially failed both times

The demo-api fixture names its database for a fingerprint over every migration's bytes **and
every seed file's bytes**, so the planted seed builds a new pair of databases
(`w1_credentials_719f1a8d259b`, `w3_demo_api_719f1a8d259b`) rather than reusing the clean
ones. In **both** attempts exactly one of that pair partially failed to build:

| attempt | database that failed | migrations that did not apply | first failure reported |
|---|---|---|---|
| 1 | `w1_credentials_719f1a8d259b` | **160 of 271** | `0066a_one_live_disposition.sql [42P01] relation "mainline.disposition" does not exist` |
| 2 | `w3_demo_api_719f1a8d259b` | **78 of 271** | `0138_trg_cue_prefix_project.sql [42P01] relation "mainline.event_cue_embedding" does not exist` |

The fixture responds by **skipping** the tests that needed that database, with a named reason
— which is why attempt 1 skipped 11 and attempt 2 skipped 8, against a baseline of 1.

**This is not caused by the plant, and it is not caused by the migrations.** Two independent
reasons, one structural and one measured:

- *Structural.* `conftest._apply_chain` applies all 271 migrations **before** any seed is
  applied. The plant edits a seed. Seed content cannot reach the migration phase; it only
  changes the database's name.
- *Measured.* A control was run for this document: the same 271 migrations, through the same
  `discover()` loop with the same per-file autocommit, into throwaway databases in W4's own
  namespace, on a clean tree with no plant present. Result: **271 applied, 0 failed — twice.**
  See [`fresh-migration-build-control.json`](../../evidence/ci/cluster-lane-2x2/fresh-migration-build-control.json).

So the migration set is sound standalone, and fails partially only when built fresh **from
inside a pytest session**, nondeterministically, at a different migration each time. The
clean-seed cells never expose it because they adopt a database built long ago.

This matters well beyond the plant: **in CI every database is fresh, in every cell.** If this
reproduces on a runner, cell 1 will drop below `CLUSTER_FLOOR` and the lane will stop there.
It is the most likely reason `cluster-lane-bites` will not reach cell 4 on its first real run,
and it should be diagnosed before that verdict is read as a fault in the 2×2.

*Owner: whoever owns `verticals/mainline/apps/demo-api/tests/conftest.py`. Not W4.*

### Finding 3 — half of the frozen-seed guard is red all the time, so its "green again" step cannot pass

`cluster-lane-bites.yml` asserts the guard twice — red with the plant, green after the revert
— *"because a guard that is red against the plant proves nothing on its own if it is red all
the time."* Measured, in this sitting:

```
with the plant:   3 failed in 0.39 s
after --revert:   2 failed, 1 passed in 0.53 s      <- NOT green
```

The two that stay red are the hash assertions, and both baselines are stale against the tree
they ship with — including for a file **this plant never touches**:

| file | `FROZEN` records | on disk today (clean, no plant) |
|---|---|---|
| `demo_world.sql` | `50535d1db0babf78…` | `e2aa9706ffca80f2…` |
| `demo_permit.sql` | `198d44ef6e843fa6…` | `df3470cb26659b4b…` |

The half that **does** discriminate is the one designed never to need re-baselining:
`test_the_seed_derives_the_demo_credentials_from_their_names` was **red with the plant and
green without it**, which is exactly the behaviour the lane claims for the whole file.

Consequence: the bites lane's *"The frozen-seed guard is GREEN again"* step will fail on the
current tree, and its *"is RED against this edit"* step proves nothing today, because that
guard is red either way.

**The remedy is not to re-baseline these hashes to make my measurement green.** That file's
own comment says a re-baseline must arrive *"in the same commit"* as the seed change that
caused it, in front of a reviewer, and that judgement belongs to the file's owner and to the
lead who owns the in-flight seed addition — not to the worker who noticed the drift while
measuring something else.

*Owner: W2 (`tests/ci/test_demo_seed_is_frozen.py`). Not W4.*

### Finding 4 — both floors hold exactly, with zero margin

Neither floor was moved. Neither needed to be.

| floor | declared in `cluster-lane-bites.yml` | measured | margin |
|---|---|---|---|
| `HERMETIC_FLOOR` | `7` | 7 (cell 2), 7 (cell 3) | **0** |
| `CLUSTER_FLOOR` | `77` | 77, 77, 77, 77 (cell 1 ×4) | **0** |

Both are satisfied at exactly their declared value, in every attempt. A floor with zero
margin is doing its job — but it is worth stating plainly that **any test in this subset that
starts skipping takes the lane below its floor immediately.** Finding 2 is exactly such an
event: cell 4's attempts executed 67 and 70, both below 77. The workflow does not apply
`CLUSTER_FLOOR` to cell 4 (only to cell 1), so it would not have caught that; the `caught_by`
assertion caught attempt 1 instead, which is the check that matters there.

**Neither floor may fall.** They may rise in a commit that records a measurement above them.

### Finding 5 — the plant harness's safety properties held, twice, verified by hash

The plant was applied and reverted **twice**. Both times:

```
pre-plant   demo_world.sql  sha256 e2aa9706ffca80f269edaa77e1dc8224b26b52ef6c4b666c74076bcc173787bf
planted     demo_world.sql  sha256 21f8f9c2b40051869528a83a02d5a28c3b89d1668fc4492dfa216708baace179
post-revert demo_world.sql  sha256 e2aa9706ffca80f269edaa77e1dc8224b26b52ef6c4b666c74076bcc173787bf   -> BYTE FOR BYTE
```

and after each revert: `--status` → *"no plant is present"* (exit 0), `.plant-cluster-defect/`
removed, the anchor line present exactly once, and the replacement hex string present **zero**
times anywhere in the file. The final state of the tree is recorded in §7.

The `--revert` step was written to run unconditionally in this worker's scripts, with no
`set -e` in the enclosing shell, precisely so that a red cell could not skip it. It did not
need to be exercised that way, but it was available both times.

---

## 6. What could NOT be measured here, stated rather than faked

**The workflow's cleanliness assertions are CI-only and were not exercised.** The bites lane
brackets the plant with `git diff --exit-code` and an empty `git status --porcelain`, before
and after. This working tree is dirty by a wide margin — **52 modified and 42 untracked files
when this sitting opened, 51 and 42 when it closed** (the difference is other workers editing
the same tree concurrently, not this worker; the counts exclude the `evidence/ci/` directory
created here) — including 493 uncommitted added lines in `demo_world.sql` itself from another
lead's in-flight change. Both assertions would fail here for reasons that have nothing to do
with the plant.

They are therefore **not evaluated in this document, and nothing here should be read as
evidence that they pass.** They will be validated when W1's repaired lane runs on a clean
checkout, and that verdict is the only one that counts for them.

What was measured instead is the strongest local substitute, and it is weaker: the SHA-256 of
the edited file before and after, plus the harness's own `--status`, plus a grep for the
planted string. Those catch a plant that survived in the file. They do **not** catch an
untracked leftover elsewhere in the tree, which is the second of the two ways a plant
survives and is exactly why the workflow uses `git status --porcelain` rather than
`git diff`. That substitution must not be made in the workflow.

Two further limits, for the same reason:

- **`--crdb=reuse` against a long-lived local node is not `--crdb=reuse` against a fresh
  container.** Every clean-seed cell here adopted a cached database. Finding 2 is the
  consequence, and it means cells 1 and 2 as measured here are *easier* than their CI
  equivalents, not harder.
- **The tree moved underneath this measurement.** `test_reads.py` and
  `qa/cluster-known-red.json` were modified by another worker at 04:22 and 04:23, between the
  before and after full-suite runs recorded in §7. The subset this document measures does not
  include `test_reads.py`, and the eight cell artefacts were all written between 04:14 and
  04:30 against a `demo_world.sql` whose hash never changed except while planted — but the
  full-suite delta in §7 is **not** attributable to this worker, and is not claimed as such.

---

## 7. Full-suite `--crdb=reuse`, before and after

Both from `--junitxml`, whole `verticals/mainline/apps/demo-api/tests` directory.

| | collected | executed | skipped | failures | errors | passed | rc | wall |
|---|---|---|---|---|---|---|---|---|
| before (04:12) | 528 | 527 | 1 | 0 | **63** | **464** | 1 | 47.10 s |
| after (04:29) | 528 | 527 | 1 | 1 | **1** | **525** | 1 | 48.58 s |

**This improvement is not this worker's.** W4 changed no code, no test, no fixture, no seed,
no floor and no threshold — the only files written are `docs/ci/cluster-lane-falsifiability.md`
and the contents of `evidence/ci/cluster-lane-2x2/`. The 63 `commit_v2` errors were resolved
by another worker's edit to `test_reads.py` at 04:22, mid-measurement. It is recorded here
because the wave requires a before and an after, and an unattributed 61-test swing in a
shared tree is worth naming rather than quietly banking.

The two remaining reds in the "after" run:

- `test_transitions.py::test_sign_disposition_hands_the_shared_connection_back_in_autocommit`
  — ERROR, the same unretried `40001` as finding 1.
- `test_reads.py::test_the_disposition_carries_the_lattice_and_the_projected_requirements`
  — FAIL, in the module another worker was editing at the time.

The lead's baseline for this wave was **524 / 523 / 1 / 6 / 63 / 454**. The tree has moved
past it in both directions since; the pair above is the honest current reading.

---

## 8. Superseded: the 2026-08-13 readings

Kept, not deleted, per the convention this repository already uses for a measurement that has
been re-taken. These were reported by the CI-runs-the-cluster wave **without artefacts**, and
this document supersedes them:

```
cell 1  77 passed, 1 skipped in 23.08 s
cell 2   7 passed, 71 skipped in 0.60 s
cell 3   7 passed, 71 skipped in 0.93 s
cell 4   3 failed, 74 passed, 1 skipped in 175.44 s
        FAILED test_credentials.py::…_used_to_derive
        FAILED test_gate_run.py::test_the_admission_is_a_green_this_database_could_have_refused
        FAILED test_gate_run.py::test_the_deployed_seed_and_the_proof_seed_are_two_different_worlds
```

What today's re-measurement changes about them:

- **Cells 1, 2 and 3 reproduce.** The executed counts are identical (77 / 7 / 7) and cell 3
  still matches cell 2.
- **Cell 4 does not reproduce as stated.** The 2026-08-13 reading has all three failures
  present at once with only the one jsonschema skip; neither attempt today reproduced that.
  Attempt 1 skipped `caught_by` entirely; attempt 2 failed `caught_by` alone and skipped the
  two `test_gate_run.py` controls. Finding 2 explains why the difference is possible, and the
  older reading is plausible as the case where **both** fresh builds happened to succeed.
- **The old §5 claim that the frozen-seed guard returns `3 passed in 0.29 s` after the revert
  is no longer true** — it is `2 failed, 1 passed`. See finding 3.

---

## 9. The plant, and the argument the 2×2 makes — unchanged, and re-verified today

`scripts/ci/plant_cluster_defect.py --plant seed-credential-swap` replaces one line of
`verticals/mainline/db/seeds/demo/demo_world.sql`, at line 124:

```sql
-    digest('mainline-demo/credential/demo.signer', 'sha256'),
+    decode('<sha256 of b"credsigner">', 'hex'),
```

This is not an invented defect; it is the **reverted** one. `gate_run` once bound
`sha256(b"credsigner")` as `signer_credential_id` while the deployed seed enrolled
`digest('mainline-demo/credential/demo.signer','sha256')`, and
`mainline.disposition.signer_credential_id` is a foreign key onto
`mainline.signing_credential (credential_id)` — so beat 4 failed `23503` against the database
that ships while the suite was green. A worker sent to fix it edited **the seed** to enrol the
constant the application derived, making the SEED match the CODE. Three negative controls
caught it. The database owns `credential_id`; the code reads it.

The replacement is **derived** in the harness (`hashlib.sha256(b"credsigner").hexdigest()`),
never written out as a literal — a second copy of a 32-byte constant is the defect class this
area of the repository keeps closing.

**The `transitions.py` reversion remains the wrong plant** and must not be added to the
catalogue: `test_no_module_derives_a_credential_id` is an AST walk that catches it statically
under `--crdb=none`. §3 confirms that ratchet executed and passed in both hermetic cells, so
it would indeed have gone red on a code plant and collapsed the argument into *"we planted
something both lanes can see."*

The harness's hygiene properties — snapshot-and-hash before touching the file, refuse to plant
over a plant, refuse an anchor matching zero or more than one line, refuse to revert a file
that changed while planted, re-hash after restoring, remove the snapshot directory, and never
use `git checkout --` (which restores from the index and would discard another lead's 493
uncommitted lines in this very file) — were exercised across two plant/revert cycles today and
held. Finding 5 records the hashes.

---

## 10. What a reader should take from this

1. **The hermetic lane provably cannot see this defect.** Cells 2 and 3 executed the same seven
   tests, by name, and all seven passed in both. Two hermetic controls whose names suggest they
   should have caught it ran and could not.
2. **The cluster lane does see it.** Cell 4 attempt 2 failed exactly one test, and it is the
   one the plant's own manifest names.
3. **The lane's refusal to accept an ambiguous red is not decoration.** Attempt 1 was red with
   two genuine plant-caused failures, and the workflow would still have refused it, because the
   named control had been skipped. Do not weaken that check to "non-zero is enough".
4. **Two defects stand between this lane and a green run in CI**, and neither is in a file this
   worker owns: an unretried `40001` in `test_transitions.py::_seed_permit` (finding 1) and a
   fresh-database build that partially fails from inside a pytest session (finding 2).
5. **One assertion in the lane cannot pass on the current tree** — the frozen-seed guard's
   "green again" half, because its two recorded hashes are stale (finding 3).
6. **Nothing was moved to obtain any of the above.** No floor, no ceiling, no fixture, no seed,
   no expected value. Where a control disagreed with the tree, the disagreement is written down
   above and the control was left alone.
