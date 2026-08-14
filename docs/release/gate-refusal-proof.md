<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# The gate-refusal proof — RED, GREEN, and then a stronger sentence

**Workers:** `qr-gate-refusal-proof` (2026-08-09) · `W8 producer-completion` (2026-08-10)
**Cluster for every transcript below:** the local single-node Docker container
`mainline-crdb`, **CockroachDB CCL v26.2.5** (x86_64-pc-linux-gnu, built 2026/07/28,
go1.25.5). **Interpreter:** `.venv/Scripts/python.exe`, **Python 3.13.14**.
**Every block on this page is verbatim stdout.** Nothing is paraphrased and nothing is
trimmed except where a line is marked `[…]`.

> Three notes on fidelity, so that "verbatim" means something:
>
> * The host's UTC clock read `2026-08-09T21:0x` on the day the working date was
>   2026-08-10. The timestamps are as the machine emitted them, not corrected to the
>   date in the brief. A transcript that has been adjusted is no longer a transcript.
> * The Windows console rendered the em-dashes and middots in the program's output as
>   replacement characters. They are restored to `—` and `·` here. That is the only
>   character-level edit on this page, and it is a fact about the terminal's code page
>   rather than about the program's output.
> * §3's shape-test run carries `-p no:trappoint_testkit`. Between the first red run and
>   the first green run another worker landed `packages/trappoint-testkit`, and for a
>   window the root `conftest.py` registered its plugin a second time under a different
>   name, which aborted **every** `pytest` invocation in the repository during collection
>   with `ValueError: Plugin already registered under a different name`. That worker has
>   since guarded it. The transcript keeps the flag where it was actually used.

---

## 0. What is being proven

On 2026-08-09 the claim was:

> **The database refuses a permit merge when a recalled precursor carries no signed
> disposition — and admits the same merge once a disposition is signed.**

Since 2026-08-10 it is strictly stronger, and every clause of it is a value in the
evidence file rather than a sentence in this one:

> **The trigger projected the counter, emitted the CDC signal, bumped the epoch, and the
> gate refused** — and admitted the same merge once a disposition was signed.

The artefacts:

| Path | What it is |
|---|---|
| `scripts/proof/gate_refusal.py` | Builds a throwaway database, bootstraps, applies the whole migration tree continuing past failures, measures the projection, attempts the merge three times, writes the evidence. |
| `tests/release/test_gate_refusal_proof.py` | Runs it and asserts each half separately. |
| `.github/workflows/release-proof.yml` | The same on a pinned `cockroachdb/cockroach:v26.2.5` with `gc.ttlseconds=4500`, uploading the evidence JSON. |
| `evidence/gate-refusal/proof-<utc>.json` | The transcript, per run. |

## 0.1 The three states of this proof, in one table

**The old numbers are kept, not deleted.** A documented before/after is worth more than
either half on its own, and a repository that quietly replaces its weaker evidence has
made its stronger evidence unfalsifiable.

| When | Chain | Projection | Caveats | Verdict | Evidence |
|---|---|---|---|---|---|
| 2026-08-09 21:07Z | **244 / 261**, 17 failed — **2 of them unexplained** (`0049z` `42601`, `0149z` `42P01` cascade) | not measured | 2 | **NOT PROVEN** | §2 |
| 2026-08-09 21:38Z | **246 / 261**, 15 failed, all attributable to five tables with no producer | not measured | 2 | PROVEN | `proof-20260809T213857Z.json` |
| 2026-08-10 05:44Z | **271 / 271**, **0 failed** | **10 / 10 assertions held** | **0** | PROVEN | `proof-20260810T054407Z.json` |
| **2026-08-14 03:24:18Z** | **271 / 271**, `failed_count: 0`, 71.797 s | held | **`caveats: []`** | **PROVEN**, `failures: []` | **`proof-20260814T032418Z.json`** |

**The fourth row was added 2026-08-14 by D3 and no earlier row was touched.** It is a
re-proof rather than a new claim: the same four beats, the same SQLSTATEs — `refusal` `23514`
`gate_closed_when_issued` (reported), `drift_refusal` `P0001`
`mainline.fn_permit_merge_gate` (parsed), `admission` `00000` — re-run after the seeds beneath
it moved. **A proof whose inputs changed and which was not re-run is a proof about a tree that
no longer exists**, which is why the row exists at all rather than the 08-10 row simply being
left to stand in for today.

> **The boundary this table must not be read across.** Every row above, including the new
> one, has `cluster.database = w_qr_gate_refusal_proof` — a **local** single-node CockroachDB
> CCL v26.2.5. **None of them is a CockroachDB Cloud result.** The repository does now hold
> two Cloud artefacts (`evidence/deploy/cloud-chain.json`, `evidence/deploy/cloud-seed.json`),
> and neither is a four-beat gate-run. `docs/CI-STATE.md` §1.0.4 states in full what is
> carried and what is still OWED, in the wording three documents share.

The middle row is the one this page used to end on. It was an honest green about a
narrower claim: the chain applied *except for gaps it could name*, and `open_blocking`
was written by the proof script because the trigger that should have written it could not
apply. Both of those are now false, and the difference is §4 onward.

---

## 1. The one file in the way (2026-08-09)

`0049z_meas_mutation_result.sql` declared, at what was line 79:

```sql
  family            STRING NOT NULL,
```

**`FAMILY` is a reserved keyword in CockroachDB** — it introduces a column family, and
`0024_commit_obj.sql` and `0029_clause_version.sql` both use it that way three files
apart. The parser reads the bare word as the keyword and the file returns `42601`. Its
allocation key `(49, "z")` sorts **before** `(50, "")`, so a forward-only runner that
stops on first error never reaches `0050_permit.sql`, let alone `0115`. One parse error
stood between this repository and its central claim.

Quoting is **not** the repair, and that was measured rather than assumed:

```
CREATE TABLE fam_probe (id INT PRIMARY KEY, family STRING NOT NULL)    -> 42601
CREATE TABLE fam_probe (id INT PRIMARY KEY, "family" STRING NOT NULL)  -> OK
INSERT INTO fam_probe (id, family)  VALUES (1,'x')                     -> 42601
INSERT INTO fam_probe (id, "family") VALUES (2,'y')                    -> OK
SELECT id, family FROM fam_probe                                       -> 42601
SELECT id, "family" FROM fam_probe                                     -> OK
UPDATE fam_probe SET family = 'z' WHERE id = 1                         -> 42601
```

`mainline_mutation/sql.py` builds its INSERT by joining a frozen column tuple, so the
bare name would have reached the statement text at run time. Quoting the DDL would have
moved the failure from migration time to run time, which is strictly worse. **The column
is renamed to `mutation_family`.** The Python attribute stays `MutantResult.family`: it
is a dataclass field, never a SQL identifier, and `RESULT_COLUMNS` is the single place
the two vocabularies meet.

---

## 2. RED #1 — before the fix

`tests/release/test_gate_refusal_proof.py`, run against the live node with the tree
exactly as found.

```
$ export MAINLINE_TEST_DSN="postgresql://root@127.0.0.1:26257/defaultdb?sslmode=disable"
$ python -m pytest tests/release/test_gate_refusal_proof.py --no-header -q --tb=line
```

```
RUN STARTED 2026-08-09T21:07:00Z
.F.....F                                                                 [100%]
================================== FAILURES ===================================
E   AssertionError: 2 migration(s) failed for a reason that is not one of the enumerated unproduced tables ['mainline_ops.outbox', 'mainline.identity_assignment', 'mainline.patrol_run', 'mainline_meas.agent_action', 'mainline_meas.standing']:
      [
        {
          "version": "0049z_meas_mutation_result",
          "sqlstate": "42601",
          "message": "at or near \"not\": syntax error DETAIL: source SQL: CREATE TABLE mainline_meas.mutation_result ( run_id UUID NOT NULL, mutant_id STRING NOT NULL, -- blake2b(seed || class || fixture), 32 hex kind STRING NOT NULL, -- 'KILL' | 'SURVIVE' class_id STRING NOT NULL, fixture_id STRING NOT NULL, family STRING NOT NULL, ^ HINT: try \\h CREATE TABLE",
          "classification": "unexplained",
          "unproduced_table": null
        },
        {
          "version": "0149z_trg_mutation_result_append_only",
          "sqlstate": "42P01",
          "message": "relation \"mainline_meas.mutation_result\" does not exist",
          "classification": "unexplained",
          "unproduced_table": null
        }
      ]
[…]
      chain         244/261 applied, 17 failed, 44.732s
      reached 0115  True
        ! UNEXPLAINED 0049z_meas_mutation_result [42601] at or near "not": syntax error […]
        ! UNEXPLAINED 0149z_trg_mutation_result_append_only [42P01] relation "mainline_meas.mutation_result" does not exist
        - no producer 0121_trg_check_materialised [42P01] needs mainline_ops.outbox
        - no producer 0145a_trg_cbm_account_guard [42P01] needs mainline.identity_assignment
        - no producer 0163_v_fixity_coverage [42P01] needs mainline.patrol_run
        - no producer 0164_v_agent_actions [42P01] needs mainline_meas.agent_action
        - no producer 0165_v_gate_latency_daily [42P01] needs mainline_meas.agent_action
        - no producer 0166_v_txn_restart_daily [42P01] needs mainline_meas.agent_action
        - no producer 0171_v_standing_components [42P01] needs mainline_meas.standing
        - no producer 0172_v_my_record [42P01] needs mainline_meas.standing
        - no producer 0187_standing_rls_enable [42P01] needs mainline_meas.standing
        - no producer 0187a_standing_rls_force [42P01] needs mainline_meas.standing
        - no producer 0187b_policy_standing_blind [42P01] needs mainline_meas.standing
        - no producer 0187c_policy_standing_assay_read [42P01] needs mainline_meas.standing
        - no producer 0187d_policy_standing_assay_insert [42P01] needs mainline_meas.standing
        - no producer 0187e_policy_standing_view_owner_read [42P01] needs mainline_meas.standing
        - no producer 0198x_no_rls_on_cdc_sources [42P01] needs mainline_ops.outbox
      REFUSAL       REFUSED [23514] gate_closed_when_issued (reported)
      DRIFT         REFUSED [P0001] mainline.fn_permit_merge_gate (parsed)
      ADMISSION     ADMITTED [00000]
      caveat        17 of 261 migrations did not apply. […]
      caveat        mainline.permit.open_blocking was written by this script, not by the check_materialised trigger, because 0121_trg_check_materialised.sql could not apply (mainline_ops.outbox has no migration). […]
      VERDICT       NOT PROVEN
=========================== short test summary info ===========================
FAILED tests/release/test_gate_refusal_proof.py::test_no_migration_failed_for_an_unexplained_reason
FAILED tests/release/test_gate_refusal_proof.py::test_the_proof_exits_zero
2 failed, 6 passed in 63.95s (0:01:03)
RUN FINISHED 2026-08-09T21:08:06Z
```

### Read this red carefully, because it is the interesting one

Two tests failed and **six passed** — and the six that passed include the refusals. That
is not an accident of ordering; it is what the proof is designed to distinguish.

* The gate was **already refusing correctly** on the unfixed tree, because
  `gate_refusal.py` continues past a failing migration and therefore still applies `0050`
  and `0115`. `trappoint migrate up` would have stopped at `0049z` and reported nothing at
  all about the gate.
* What was red is a **different claim**: that the schema this repository ships applies
  cleanly except for gaps it can name. `42601` on `0049z` is not a nameable gap, so the
  verdict is `NOT PROVEN` even though every refusal landed.

Keeping those two claims apart is the whole design, and it is the same design that makes
§6 below readable.

---

## 3. The fix, and GREEN #1 — the before-state, kept

Three files: `0049z` (`family` → `mutation_family`), `mainline_mutation/sql.py`
(`RESULT_COLUMNS`), and two new shape tests in `tests/e2e/mutation/test_sql_shape.py`
that refuse any column spelled with a CockroachDB reserved keyword.

```
$ python -m pytest tests/e2e/mutation/test_sql_shape.py --no-header -q -p no:trappoint_testkit
.......................                                                  [100%]
23 passed in 0.62s
```

The green that followed is `evidence/gate-refusal/proof-20260809T213857Z.json`:

```
RUN STARTED 2026-08-09T21:38:57Z
cluster       CockroachDB CCL v26.2.5 (x86_64-pc-linux-gnu, built 2026/07/28 18:56:00, go1.25.5)
database      w_qr_gate_refusal_proof
chain         246/261 applied, 15 failed, 57.23s
reached 0115  True
  - no producer 0121_trg_check_materialised [42P01] needs mainline_ops.outbox
  - no producer 0145a_trg_cbm_account_guard [42P01] needs mainline.identity_assignment
  - no producer 0163_v_fixity_coverage [42P01] needs mainline.patrol_run
  […twelve more, every one named…]
  - no producer 0198x_no_rls_on_cdc_sources [42P01] needs mainline_ops.outbox
REFUSAL       REFUSED [23514] gate_closed_when_issued (reported)
DRIFT         REFUSED [P0001] mainline.fn_permit_merge_gate (parsed)
ADMISSION     ADMITTED [00000]
caveat        15 of 261 migrations did not apply. […]
caveat        mainline.permit.open_blocking was written by this script, not by the check_materialised trigger, because 0121_trg_check_materialised.sql could not apply (mainline_ops.outbox has no migration). The value written is the count the gate re-derives for itself, so the refusal below is still the database's.
VERDICT       PROVEN
EXIT=0
RUN FINISHED 2026-08-09T21:40:44Z
```

**244/261 → 246/261. Two migrations, and the verdict moved from NOT PROVEN to PROVEN.**
That sentence was true and it was also the ceiling of what the artefact could then claim.
Fifteen files still did not apply, and the counter in the refusal was written by the
script.

---

## 4. What changed on 2026-08-10 — and the caveat that retired itself

The producer-completion wave authored the missing producers. Seven, not five: the census
had counted SQLSTATEs, and **CockroachDB names only the first absent relation in a
statement**, so `mainline_meas.person_measure_policy` was shadowed by
`mainline_meas.standing` in both views that join it and never appeared in an error at
all. `mainline_ops.site_register_signal` blocked no migration and only an RLS negative
assertion.

```
$ ls verticals/mainline/db/migrations/*.sql | wc -l
271
```

`0049d_identity_assignment` · `0089_agent_action` · `0089a_person_measure_policy` ·
`0089b_standing` · `0090_patrol_run` · `0099_outbox` · `0099a_site_register_signal`, plus
three append-only welds at `0145f` / `0149a` / `0149b`. **`mainline_ops.outbox`
deliberately gets no weld** — it is the one row-level-TTL table in `mainline_ops`, and a
`BEFORE DELETE` refusal trigger would make the TTL job fail forever.

Two things then happened to this proof **without a line of it being edited**, and both
were verified before anything was written about them.

### 4.1 The caveat removed itself

`seed_history()` already probed `information_schema.triggers` for `check_materialised`
and only wrote `open_blocking` by hand when the probe came back false; the caveat was
conditional on the same flag. Running the *unmodified* script against the new tree:

```
$ .venv/Scripts/python.exe scripts/proof/gate_refusal.py \
    --dsn postgresql://root@localhost:26257/defaultdb?sslmode=disable --database w_W8_baseline
chain         271/271 applied, 0 failed, 63.309s
reached 0115  True
REFUSAL       REFUSED [23514] gate_closed_when_issued (reported)
DRIFT         REFUSED [P0001] mainline.fn_permit_merge_gate (parsed)
ADMISSION     ADMITTED [00000]
VERDICT       PROVEN
```

```
caveats []
unproduced ['mainline_ops.outbox', 'mainline.identity_assignment', 'mainline.patrol_run',
            'mainline_meas.agent_action', 'mainline_meas.standing']
files 271 applied 271 failed 0
trigger True
counter_source trigger check_materialised -> mainline.fn_check_materialised
```

Both caveats gone; `271/271`; the counter written by the trigger. **That is the whole of
what "retire the caveat" would have delivered, and it delivered itself.** Note what is
still wrong in that output: `unproduced` still enumerates five tables that now all exist,
which means the proof was still willing to forgive a failure attributable to any of them.

### 4.2 The ratchet: `UNPRODUCED_TABLES` is now `()`

`apply_chain` classifies a failure as *explained* only when it is attributable to a listed
table. An empty tuple therefore turns **any** residual failure into
`chain.failures_unexplained`, which is a hard NOT PROVEN. The list is emptied, the release
test's five-table tolerance is **deleted rather than narrowed**, and
`test_no_table_is_left_without_a_producer` now asserts the list stays empty — so
re-populating it to make a red run green fails a test before it hides anything.

---

## 5. The stronger sentence — the `projection` block

Removing an apology is a subtraction. The deliverable is the addition: read back the
evidence that the **trigger** did the work, and make every clause of it an assertion that
can fail.

`mainline.permit` is read immediately before and immediately after the single
`INSERT INTO mainline.blocking_check`, **with no other statement in between**, so the
delta is attributable to the weld and to nothing else in the seed. Then
`mainline_ops.outbox` is read back for the row the trigger emitted.

Verbatim from `evidence/gate-refusal/proof-20260810T054407Z.json`:

```json
{
  "claim": "the trigger projected the counter, emitted the CDC signal, bumped the epoch, and the gate refused",
  "trigger": { "name": "check_materialised", "timing": "AFTER INSERT",
               "on": "mainline.blocking_check",
               "function": "mainline.fn_check_materialised",
               "migration": "0121_trg_check_materialised.sql", "present": true },
  "fired_by": "one INSERT INTO mainline.blocking_check, with no other statement between the before and after readings",
  "open_blocking": { "before": 0, "after": 1, "expected_after": 1 },
  "gate_epoch":    { "before": 0, "after": 1, "moved": true },
  "severity": { "supplied_by_this_script": 0, "projected_onto_the_check": 4,
                "virulence_projected": "blood_major", "closure_gen_projected": 0 },
  "outbox": {
    "relation": "mainline_ops.outbox", "relation_present": true,
    "rows_in_table": 1, "rows_for_this_check": 1, "expected_kind": "check_opened",
    "row": {
      "signal_id": "1906c6b6-3a55-40a3-aa5e-9b44df2f6c8b",
      "kind": "check_opened",
      "subject_id": "c211d4dc-65c6-4254-8912-3d48a3991908",
      "site_id": "83a3e243-3c46-45f2-85c7-11ad2b636e06",
      "target_site": null, "activity_root": null,
      "max_severity": 4, "score": "0", "payload": {},
      "emitted_at": "2026-08-10T05:45:31.693997+00:00",
      "expires_at": "2026-09-09T05:45:31.693997+00:00"
    }
  },
  "assertions_held": 10, "assertions_total": 10
}
```

`subject_id` is the `check_id` in `history.blocking_check_id`, character for character.
`rows_in_table` is `1`: the entire seeded history emitted exactly one CDC signal, and it
is this one.

### The three clauses worth arguing about

* **`gate_epoch` 0 → 1, strictly.** MI07. The completion record's composite FK carries
  `ON UPDATE RESTRICT`, so moving the epoch is what makes attaching a precursor to an
  already-issued subject *physically* impossible rather than merely disallowed. An epoch
  that stands still is a pin that does not pin, which is why the assertion is `after >
  before` and not `after >= before`.
* **`max_severity` is 4 and the script supplied 0.** This is the sharpest value on the
  page, because it demonstrates an *ordering* rather than a fact. `fn_check_project`
  (BEFORE INSERT, 0120) overwrites the client's `severity` from `clause_blame_current`;
  `fn_check_materialised` (AFTER INSERT, 0121) copies `(NEW).severity` into the signal. A
  `4` in the outbox proves both triggers ran and proves which ran first.
* **`payload` is `{}`.** Pointers and digests only. A changefeed bypasses row-level
  security entirely, so every byte in that column is readable by anything that can read
  the feed, and `mainline_ops.outbox` has no policy to fall back on by construction
  (§4.1 law 11: exactly one changefeed-query source).

---

## 6. RED #2 — the projection assertions, observed failing

PL-2 again: an assertion that has never been red asserts nothing. The tree was copied to a
scratch directory with **`0121_trg_check_materialised.sql` removed** — the weld, not the
table — and the proof was pointed at the copy with `--migrations`. `mainline_ops.outbox`
still exists, so the chain still applies in full; only the projection is gone.

```
$ cp -r verticals/mainline/db/migrations $SCRATCH/tree_no_0121
$ rm $SCRATCH/tree_no_0121/0121_trg_check_materialised.sql
$ .venv/Scripts/python.exe scripts/proof/gate_refusal.py \
    --dsn postgresql://root@localhost:26257/defaultdb?sslmode=disable \
    --database w_W8_red --migrations $SCRATCH/tree_no_0121 --out $SCRATCH/red.json
```

```
cluster       CockroachDB CCL v26.2.5 (x86_64-pc-linux-gnu, built 2026/07/28 18:56:00, go1.25.5)
database      w_W8_red
chain         270/270 applied, 0 failed, 58.938s
reached 0115  True
unproduced    (none) — every relation this tree references has a producer
PROJECTION    1/10 held · open_blocking 0->0 · gate_epoch 0->0 · outbox None severity None (client supplied 0)
  ! trigger_present: present=False
  ! counter_source_is_the_trigger: scripts/proof/gate_refusal.py — the check_materialised trigger is ABSENT from this schema, so 0121_trg_check_materialised.sql did not apply. […]
  ! open_blocking_projected: 0 -> 0
  ! gate_epoch_strictly_increased: 0 -> 0
  ! outbox_row_emitted: rows_for_this_check=0
  ! outbox_kind_is_check_opened: None
  ! outbox_subject_is_the_check: None vs check_id 39eb5987-3847-4431-9590-3bfe3b83a3c7
  ! outbox_site_is_the_seeded_site: None vs site_id 66571be9-423c-4a88-900c-ff1428f03b26
  ! outbox_max_severity_is_the_projected_severity: emitted=None projected=4 supplied=0
REFUSAL       REFUSED [23514] gate_closed_when_issued (reported)
DRIFT         REFUSED [P0001] mainline.fn_permit_merge_gate (parsed)
ADMISSION     ADMITTED [00000]
caveat        mainline.permit.open_blocking was written by this script, not by the check_materialised trigger, because that trigger is absent from this schema (0121_trg_check_materialised.sql did not apply). […] the projection is NOT proven, and projection.assertions names every clause that failed.
  ! projection.trigger_present: […]
  […nine failures, each naming its clause and the value observed…]
VERDICT       NOT PROVEN
EXIT=1
```

**Nine of ten assertions failed and all three refusal beats still landed.** That is the
design, not a leak: the run does not abort on a broken projection, because "the gate
refused but nothing projected it" and "the gate admitted the merge" are different
findings and the reader has to be able to tell them apart. The one assertion that held
was `outbox_relation_present` — the table exists; nothing wrote to it.

The caveat is still emitted on this path, because on this path something genuinely *is*
unproven and the hand-written counter needs explaining. It is emitted **alongside** the
failure, not instead of it.

---

## 7. GREEN #2 — the record run

```
$ .venv/Scripts/python.exe scripts/proof/gate_refusal.py \
    --dsn postgresql://root@localhost:26257/defaultdb?sslmode=disable --database w_W8
```

```
RUN STARTED 2026-08-10T05:44:07Z
cluster       CockroachDB CCL v26.2.5 (x86_64-pc-linux-gnu, built 2026/07/28 18:56:00, go1.25.5)
database      w_W8
chain         271/271 applied, 0 failed, 63.094s
reached 0115  True
unproduced    (none) — every relation this tree references has a producer
PROJECTION    10/10 held · open_blocking 0->1 · gate_epoch 0->1 · outbox 'check_opened' severity 4 (client supplied 0)
REFUSAL       REFUSED [23514] gate_closed_when_issued (reported)
DRIFT         REFUSED [P0001] mainline.fn_permit_merge_gate (parsed)
ADMISSION     ADMITTED [00000]
caveats       (none) — nothing in this run is unproven-but-tolerated
VERDICT       PROVEN
evidence      D:\CoackroachDBxAWS\mainline\evidence\gate-refusal\proof-20260810T054407Z.json
EXIT=0
```

The `caveats       (none)` line is printed deliberately. An absent caveat line and an
empty caveat list read identically to a human, and they are not the same thing; the
release test asserts that the string is in stdout for exactly that reason.

And the release suite, with the invocation `release-proof.yml` uses:

```
$ export MAINLINE_TEST_DSN="postgresql://root@127.0.0.1:26257/defaultdb?sslmode=disable"
$ python -m pytest tests/release/test_gate_refusal_proof.py -q --no-header -p no:cacheprovider
```

```
...............                                                          [100%]
15 passed in 79.25s (0:01:19)
```

Eight tests on 2026-08-09, fifteen now. The seven added assert the projection clause by
clause, that the chain applied in full, that the enumerated-tolerance list is empty, and
that `caveats == []`.

**246/261 with two caveats → 271/271 with none, and a claim that names its own
mechanism.**

---

## 8. What the database actually said

Verbatim from `evidence/gate-refusal/proof-20260810T054407Z.json`.

### The refusal — CF-01

```json
{
  "outcome": "REFUSED",
  "sqlstate": "23514",
  "constraint": "gate_closed_when_issued",
  "constraint_source": "reported",
  "message": "failed to satisfy CHECK constraint ((state != 'merged':::mainline.subject_state) OR (open_blocking = 0:::INT8))",
  "case": "CF-01",
  "history": "one open blocking check, no signed disposition"
}
```

The exhibit is a **constraint name**, not a message. The gate trigger deliberately does
not pre-empt this CHECK: a synthetic `P0001` would carry no `constraint_name` at all, and
trading a named exhibit for an unnamed one is a strictly worse refusal
(`spec/errors.md` §3.3).

The `open_blocking = 1` this CHECK fired on is the value in §5 — the one the trigger
wrote. The refusal and the projection are now the same story told twice.

### The drift refusal — CF-03

```json
{
  "outcome": "REFUSED",
  "sqlstate": "P0001",
  "constraint": "mainline.fn_permit_merge_gate",
  "constraint_source": "parsed",
  "message": "MAINLINE: merge refused by mainline.fn_permit_merge_gate — re-derived open obligation count is 1 while the projected counter reads zero",
  "case": "CF-03",
  "history": "open_blocking forced to zero out of band; the obligation is still open"
}
```

This is the case **no CHECK can hold.** "Live disposition" carries `expires_at > now()`,
`now()` is not immutable, and a CHECK sees only the row being written. So the gate
re-derives the count from `blocking_check` anti-joined against `disposition` and refuses
on disagreement. That is rule **P-2** — *a projection is enforced, never trusted* —
demonstrated rather than asserted. Note that it refuses a counter the **trigger** wrote,
once that counter has been tampered with: the projection being trustworthy in §5 does not
make it trusted here.

`constraint_source` is `parsed`, not `reported`, because `diag.constraint_name` is empty
for `P0001` (`spec/errors.md` §3.1). The refusal ledger's own
`refusal_p0001_exhibit_is_parsed` CHECK refuses a row that claims otherwise, so this
distinction is enforced by the database and not by the script's manners.

### Both were written to the refusal ledger and read back

```json
{
  "written": true, "read_back": true,
  "refusal_id": "4086aeda-a46c-4a04-9b74-941614c1f1ce",
  "observed_at": "2026-08-10T05:45:32.377653+00:00",
  "sqlstate": "23514", "constraint_name": "gate_closed_when_issued",
  "constraint_source": "reported", "subject_kind": "permit",
  "gate_epoch": 1, "diagnosis": "declarative", "mus_cardinality": 1,
  "naa_kind": "dispose_obligations", "recorded_by": "scripts/proof/gate_refusal.py"
}
```

`mainline.refusal_ledger` carries `refusal_payload_names_the_exhibit`,
`refusal_payload_names_the_code`, `refusal_payload_names_the_subject` and
`refusal_mus_agrees`. **A row that misdescribes the refusal it records cannot be
inserted.** A refusal this script had invented would have been refused by the table that
stores refusals.

`gate_epoch: 1` is the same epoch the trigger produced in §5, and the release test asserts
those two values are equal — a ledgered refusal that named a different epoch than the
projection left behind would mean the two halves disagree about what was refused.

### The admission

```json
{
  "signed": true,
  "disposition_id": "80b8da7a-31d9-4154-a614-f1b1358cee6a",
  "kind": "applied",
  "virulence_projected": "blood_major",
  "signer_rank_projected": 5,
  "reading_floor_met_projected": true,
  "deliberation_seconds_projected": 601,
  "permit_open_blocking_after": 0,
  "permit_unmet_floor_count_after": 0,
  "permit_countersigned_count_after": 1
}
```

Note `virulence_projected`. The script inserted `'routine'` and the database wrote
`'blood_major'`, read through the blocking check to the blame closure — finding S1, and
the reason a signer cannot choose which row of the clearance lattice judges their own
signature. `reading_floor_met` and `deliberation_seconds` are likewise the server's
arithmetic over a receipt issued ten minutes earlier, not a client's claim.

```json
{
  "outcome": "ADMITTED", "sqlstate": "00000",
  "merge_record": {
    "present": true, "subject_kind": "permit", "gate_epoch": 1,
    "merged_by": "proof.signer",
    "merged_commit": "93bb35d778549a7d35b210b04612e80a9ecc88c84630a6b32e7340eda97a04ae",
    "clearance_digest": "eef67f8c994c41bd5adf1eb9476dc84b10902612f6e19bc314b60cb48649ab4b",
    "merged_at": "2026-08-10T05:45:32.876050+00:00",
    "permit_state": "merged", "permit_open_blocking": 0,
    "event_chain": [
      {"seq": 1, "from": "draft",               "to": "checks_materialised", "chain_digest": "ff92e576…"},
      {"seq": 2, "from": "checks_materialised", "to": "dispositioned",       "chain_digest": "03c06e37…"},
      {"seq": 3, "from": "dispositioned",       "to": "merged",              "chain_digest": "…"}
    ]
  }
}
```

**This half matters as much as the refusal.** A gate that always refuses is a broken gate,
not a safe one, and a release test asserting only the refusal would stay green against a
schema in which nothing can merge at all. `clearance_digest` is computed server-side over
the sorted `(check_id, disposition_id)` set: exactly which obligations were cleared, by
which signatures, at the instant of the merge.

---

## 9. The history that was seeded, and why each part had to be there

The permit is walked `draft → checks_materialised → dispositioned` through its own
hash-chained event log **before** the merge is attempted. That last edge is the client
asserting that every obligation now carries a signed disposition. It does not. **The
client lies about the state and the database catches it** — which is a sharper
demonstration than a permit that never claimed to be ready.

Reaching the gate at all meant walking real trigger chains rather than around them:

* `fn_closure_guard` requires the first closure generation for a clause version to be
  **zero**, and ledgers the closure into `ledger_intake` in the same transaction.
* `fn_check_project` overwrites the supplied `severity`/`virulence`/`closure_gen` from
  `clause_blame_current` and **raises** if there is no closure — a check cannot be armed
  against a clause whose ancestry has not been computed. Since 2026-08-10 the proof reads
  that overwrite back and compares it against the outbox row (§5).
* `mainline_meas.silence_receipt` is what an exposure receipt must point at; a silence
  receipt belongs to a `recall_run`; and `fn_recall_policy_anchored` refuses a run whose
  policy anchor is not inside a **cosigned checkpoint**. So the proof seeds a
  `ledger_checkpoint` and a `cosignature` too. The recall pass that found the precursor is
  a real row, not a narrative flourish.
* `fn_permit_merge_gate` additionally demands an authority-source row for every cited
  clause version and a boundary certificate for the permit; `z_cbm_gate` demands a
  balanced `cbm_account` for every cited commit. All three are satisfied, which is why the
  refusal that fires is the one about the open obligation and not an incidental one.

One quirk is recorded rather than worked around: `fn_recall_policy_anchored` compares
`ledger_checkpoint.site_code` against `(NEW).site_id::STRING`, so the seeded site's
`site_code` **is** its `site_id`. Renaming the seam to make the fixture prettier would
have been proving a different schema.

---

## 10. What is NOT proven, stated plainly

1. **This is a census runner, not a deployment runner.** `gate_refusal.py` applies each
   file in its own transaction and continues past failures, which is why it could report
   246/261 on a tree that `trappoint migrate up` halted at file 156. `271/271, 0 failed`
   here means *every file applied when applied independently*. The forward-only,
   attested, one-uninterrupted-run claim through `trappoint migrate up` belongs to the
   chain lane's own release note and is **not** made on this page. Do not quote
   `271/271` as a deployment result; quote it as what it is, a census.

2. **This is two conformance cases, not seventy-one.** CF-01 and CF-03 of a manifest with
   71. The rest belong to `trappoint-conform`; this lane proves the central claim, not the
   suite.

3. **One CDC signal is not a changefeed.** The proof reads the row the trigger wrote into
   `mainline_ops.outbox` directly. It does not create a changefeed, does not consume one,
   and therefore proves that the *emitter* works, not that the transport does. Saying "the
   trigger emitted the CDC signal" is exact; saying "the CDC pipeline works" would not be.

4. **Two clusters, not one.** Every transcript here is the local single-node container.
   Nothing on this page has been run against CockroachDB Cloud. `release-proof.yml` runs
   it on a pinned `cockroachdb/cockroach:v26.2.5` with `gc.ttlseconds` pinned to **4500**
   — Cloud's value, tighter than the local default of 14400 — so a time-travel assumption
   that survives a laptop still has to survive CI.

5. **The `localhost` DSN costs 130 seconds per connection on this host.** Measured:
   `localhost` resolves to `::1` first, nothing answers there, and libpq waits out the OS
   TCP timeout. The proof sets `connect_timeout` (default 10s, `--connect-timeout`) and
   reuses one connection for the whole run. That is a fix to the harness, not to the
   product.

---

## 11. Reproducing this

```bash
docker run -d --name mainline-crdb -p 26257:26257 cockroachdb/cockroach:v26.2.5 \
  start-single-node --insecure

python scripts/proof/gate_refusal.py \
  --dsn postgresql://root@localhost:26257/defaultdb?sslmode=disable
echo $?   # 0 == PROVEN

export MAINLINE_TEST_DSN="postgresql://root@127.0.0.1:26257/defaultdb?sslmode=disable"
python -m pytest tests/release/test_gate_refusal_proof.py -q
```

To watch it go red again on purpose, pick the half you want to break:

```bash
# break the CHAIN: put `family` back in 0049z, or delete any migration between 0050 and 0130.
#   -> chain.failures_unexplained stops being empty. NOT PROVEN.

# break the PROJECTION: copy the tree, remove 0121_trg_check_materialised.sql, point at the copy.
cp -r verticals/mainline/db/migrations /tmp/tree_no_0121
rm /tmp/tree_no_0121/0121_trg_check_materialised.sql
python scripts/proof/gate_refusal.py --dsn "$MAINLINE_TEST_DSN" \
  --migrations /tmp/tree_no_0121 --out /tmp/red.json
#   -> PROJECTION 1/10 held, every refusal still lands, NOT PROVEN, exit 1.
```

That both halves can be broken independently, and that each says which one broke, is the
property that makes this a test rather than a demonstration.
