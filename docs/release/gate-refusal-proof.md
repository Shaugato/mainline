<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# The gate-refusal proof — RED, then GREEN

**Worker:** `qr-gate-refusal-proof` · **Date:** 2026-08-10
**Cluster for every transcript below:** the local single-node Docker container
`mainline-crdb`, **CockroachDB CCL v26.2.5** (x86_64-pc-linux-gnu, built 2026/07/28,
go1.25.5). **Interpreter:** `.venv/Scripts/python.exe`, **Python 3.13.14**.
**Every block on this page is verbatim stdout.** Nothing is paraphrased and nothing is
trimmed except where a line is marked `[…]`.

> Two notes on fidelity, so that "verbatim" means something:
>
> * The host's UTC clock reads `2026-08-09T21:0x` while the working date is 2026-08-10.
>   The timestamps are as the machine emitted them, not corrected to the date in the
>   brief. A transcript that has been adjusted is no longer a transcript.
> * The Windows console rendered the em-dashes in the assertion messages as replacement
>   characters. They are restored to `—` here. That is the only character-level edit on
>   this page, and it is a fact about the terminal's code page rather than about the
>   program's output.
> * §3's shape-test run carries `-p no:trappoint_testkit`. Between the red run and the
>   green run another worker landed `packages/trappoint-testkit`, and for a window the
>   root `conftest.py` registered its plugin a second time under a different name, which
>   aborted **every** `pytest` invocation in the repository during collection with
>   `ValueError: Plugin already registered under a different name`. That worker has since
>   guarded it (`pytest_plugins = [] if _PLUGIN in sys.modules else [_PLUGIN]`), and the
>   final green in §4 is the unmodified CI invocation with no flag. The transcript keeps
>   the flag where it was actually used.

---

## 0. What was being proven

> **The database refuses a permit merge when a recalled precursor carries no signed
> disposition — and admits the same merge once a disposition is signed.**

Until this run, nobody had demonstrated it. The migration-chain verifier's 2026-08-08
report said so honestly: the kernel gate tables did not exist when it ran. They exist
now — `0050_permit.sql`, `0058_blocking_check.sql`, `0066_disposition.sql`,
`0071_merge_record.sql`, `0071c_refusal_ledger.sql`, `0115_fn_permit_merge_gate.sql`,
`0117_proc_merge_permit.sql`, `0130_trg_permit_merge_gate.sql` — and this page is the
first record of the claim being put to a database and answered.

The artefacts:

| Path | What it is |
|---|---|
| `scripts/proof/gate_refusal.py` | Builds a throwaway database, bootstraps, applies all 261 migrations continuing past failures, seeds the history, attempts the merge three times, writes the evidence. |
| `tests/release/test_gate_refusal_proof.py` | Runs it and asserts each half separately. |
| `.github/workflows/release-proof.yml` | The same on a pinned `cockroachdb/cockroach:v26.2.5` with `gc.ttlseconds=4500`, uploading the evidence JSON. |
| `evidence/gate-refusal/proof-<utc>.json` | The transcript, per run. |

---

## 1. The one file in the way

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

## 2. RED — before the fix

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
    assert [{'version': ...lained', ...}] == []
      
      Left contains 2 more items, first extra item: {'version': '0049z_meas_mutation_result', 'sqlstate': '42601', 'message': 'at or near "not": syntax error DETAIL: sour...ixture_id STRING NOT NULL, family STRING NOT NULL, ^ HINT: try \\h CREATE TABLE', 'classification': 'unexplained', ...}
      Use -v to get more diff
D:\CoackroachDBxAWS\mainline\tests\release\test_gate_refusal_proof.py:131: AssertionError: 2 migration(s) failed for a reason that is not one of the enumerated unproduced tables ['mainline_ops.outbox', 'mainline.identity_assignment', 'mainline.patrol_run', 'mainline_meas.agent_action', 'mainline_meas.standing']:
E   AssertionError: gate_refusal.py exited 1 — verdict 'NOT PROVEN', failures [
        "2 migration(s) failed for a reason that is not one of the 5 enumerated unproduced tables: 0049z_meas_mutation_result [42601], 0149z_trg_mutation_result_append_only [42P01]"
      ]
      stdout:
      cluster       CockroachDB CCL v26.2.5 (x86_64-pc-linux-gnu, built 2026/07/28 18:56:00, go1.25.5)
      database      release_gate_refusal_proof
      chain         244/261 applied, 17 failed, 44.732s
      reached 0115  True
        ! UNEXPLAINED 0049z_meas_mutation_result [42601] at or near "not": syntax error DETAIL: source SQL: CREATE TABLE mainline_meas.mutation_result ( run_id UUID NOT NULL, mutant_id STRING NOT NULL, -- blake2b(seed || class || fixture), 32 hex kind STRING NOT NULL, -- 'KILL' | 'SURVIVE' class_id STRING NOT NULL, fixture_id STRING NOT NULL, family STRING NOT NULL, ^ HINT: try \h CREATE TABLE
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
      caveat        mainline.permit.open_blocking was written by this script, not by the check_materialised trigger, because 0121_trg_check_materialised.sql could not apply (mainline_ops.outbox has no migration). The value written is the count the gate re-derives for itself, so the refusal below is still the database's.
        ! 2 migration(s) failed for a reason that is not one of the 5 enumerated unproduced tables: 0049z_meas_mutation_result [42601], 0149z_trg_mutation_result_append_only [42P01]
      VERDICT       NOT PROVEN
      evidence      C:\Users\shaug\AppData\Local\Temp\pytest-of-shaug\pytest-491\gate-refusal0\proof.json
      
    assert 1 == 0
D:\CoackroachDBxAWS\mainline\tests\release\test_gate_refusal_proof.py:201: AssertionError: gate_refusal.py exited 1 — verdict 'NOT PROVEN', failures [
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

Keeping those two claims apart is the whole design. A proof that only asserted "the merge
was refused" would have been green on a tree whose migration chain does not apply — and
would have been telling the truth about the wrong thing.

---

## 3. The fix

Three files, and only three.

| File | Change |
|---|---|
| `verticals/mainline/db/migrations/0049z_meas_mutation_result.sql` | `family` → `mutation_family`, plus the measured reasoning for why quoting was rejected. |
| `verticals/mainline/packages/mainline-mutation/src/mainline_mutation/sql.py` | `RESULT_COLUMNS` entry `"family"` → `"mutation_family"`. The parameter tuple still reads `result.family`; that attribute is Python and stays. |
| `tests/e2e/mutation/test_sql_shape.py` | Two new tests: no column in `0049y`/`0049z` may be spelled with a CockroachDB reserved keyword, and the result table must name the column `mutation_family`. |

`0149z_trg_mutation_result_append_only.sql` does **not** reference the column. It was read
and left alone: its `42P01` was a cascade from `0049z`, not a defect of its own.

The shape test after the rename:

```
$ python -m pytest tests/e2e/mutation/test_sql_shape.py --no-header -q -p no:trappoint_testkit
.......................                                                  [100%]
23 passed in 0.62s
```

---

## 4. GREEN — the proof itself

Run with the exact DSN in the brief, `localhost` and all.

```
$ python scripts/proof/gate_refusal.py --dsn postgresql://root@localhost:26257/defaultdb?sslmode=disable
```

This is the run whose evidence file is committed as
`evidence/gate-refusal/proof-20260809T213857Z.json`. An earlier green at `21:25:48Z` was
identical in every observable except run identifiers; it was superseded only because a
lint pass over `gate_refusal.py` followed it, and a transcript that does not correspond to
the artefact on disk is worth less than one that does.

```
RUN STARTED 2026-08-09T21:38:57Z
cluster       CockroachDB CCL v26.2.5 (x86_64-pc-linux-gnu, built 2026/07/28 18:56:00, go1.25.5)
database      w_qr_gate_refusal_proof
chain         246/261 applied, 15 failed, 57.23s
reached 0115  True
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
caveat        15 of 261 migrations did not apply. Every one is listed under chain.failures_* with its file name and SQLSTATE. The five tables with no producer are named in chain.unproduced_tables_enumerated; this script does not create them, because a new table takes a number the allocation table grants and this worker owns no band.
caveat        mainline.permit.open_blocking was written by this script, not by the check_materialised trigger, because 0121_trg_check_materialised.sql could not apply (mainline_ops.outbox has no migration). The value written is the count the gate re-derives for itself, so the refusal below is still the database's.
VERDICT       PROVEN
evidence      D:\CoackroachDBxAWS\mainline\evidence\gate-refusal\proof-20260809T213857Z.json
EXIT=0
RUN FINISHED 2026-08-09T21:40:44Z
```

And the release suite, run with exactly the invocation `release-proof.yml` uses:

```
$ export MAINLINE_TEST_DSN="postgresql://root@127.0.0.1:26257/defaultdb?sslmode=disable"
$ python -m pytest tests/release/test_gate_refusal_proof.py -q --no-header -p no:cacheprovider
```

```
RUN STARTED 2026-08-09T21:35:29Z
........                                                                 [100%]
8 passed in 70.57s (0:01:10)
RUN FINISHED 2026-08-09T21:36:41Z
```

The same eight tests were `2 failed, 6 passed` in §2 and are `8 passed` here. Nothing in
the test file changed between the two runs.

Finally, the release lane together with the shape tests that hold the rename in place:

```
$ python -m pytest tests/release/test_gate_refusal_proof.py tests/e2e/mutation/test_sql_shape.py \
    -q --no-header -p no:cacheprovider
...............................                                          [100%]
31 passed in 90.15s (0:01:30)
```

**244/261 → 246/261. Two migrations, and the verdict moves from NOT PROVEN to PROVEN.**

---

## 5. What the database actually said

Verbatim from `evidence/gate-refusal/proof-20260809T212549Z.json`.

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
demonstrated rather than asserted.

`constraint_source` is `parsed`, not `reported`, because `diag.constraint_name` is empty
for `P0001` (`spec/errors.md` §3.1). The refusal ledger's own
`refusal_p0001_exhibit_is_parsed` CHECK refuses a row that claims otherwise, so this
distinction is enforced by the database and not by the script's manners.

### Both were written to the refusal ledger and read back

```json
{
  "written": true, "read_back": true,
  "refusal_id": "0f66d651-457f-46fc-be71-5eb82ca9d8bf",
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

### The admission

```json
{
  "signed": true,
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
    "clearance_digest": "98d9a4eb4affb07ef396916eb25ca7c7aa28a4bc3144bea886d07fda906bec83",
    "permit_state": "merged", "permit_open_blocking": 0,
    "event_chain": [
      {"seq": 1, "from": "draft",               "to": "checks_materialised", "chain_digest": "ff92e576…"},
      {"seq": 2, "from": "checks_materialised", "to": "dispositioned",       "chain_digest": "03c06e37…"},
      {"seq": 3, "from": "dispositioned",       "to": "merged",              "chain_digest": "cf8abbd9…"}
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

## 6. The history that was seeded, and why each part had to be there

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
  against a clause whose ancestry has not been computed.
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

## 7. What is NOT proven, stated plainly

1. **Fifteen migrations did not apply.** Every one is named in the evidence with its
   SQLSTATE and the table it needed. Five tables have consumers and no producer:
   `mainline_ops.outbox`, `mainline.identity_assignment`, `mainline.patrol_run`,
   `mainline_meas.agent_action`, `mainline_meas.standing`. **They were not created here.**
   A new table takes a number from a band whose owner and mode match in
   `migrations.allocation.toml`, and this worker owns no band. A recorded gap is a
   finding; an invented table is a lie about what the schema is.

2. **`open_blocking` was written by the proof script, not by the projection trigger.**
   `0121_trg_check_materialised.sql` is the trigger that increments it, and it cannot
   apply because its function inserts into the missing `mainline_ops.outbox`. The script
   writes the counter to the value the gate independently re-derives, and says so in
   `caveats` and in `history.open_blocking_counter_written_by`. This does not weaken
   either refusal — CF-01 is a CHECK firing on the completing row, and CF-03 is precisely
   the case where the counter is *not* trusted whoever wrote it — but a proof that stood
   in for a missing trigger without naming it would be asserting more than it measured.
   When the outbox migration lands, `projection_trigger_check_materialised_present` flips
   to `true` and the caveat disappears on its own.

3. **This is two conformance cases, not seventy-one.** CF-01 and CF-03 of a manifest with
   71. The rest belong to `trappoint-conform`; this lane proves the central claim, not the
   suite.

4. **Two clusters, not one.** Every transcript here is the local single-node container.
   Nothing on this page has been run against CockroachDB Cloud. `release-proof.yml` runs
   it on a pinned `cockroachdb/cockroach:v26.2.5` with `gc.ttlseconds` pinned to **4500**
   — Cloud's value, tighter than the local default of 14400 — so a time-travel assumption
   that survives a laptop still has to survive CI.

5. **The `localhost` DSN costs 130 seconds per connection on this host.** Measured:
   `localhost` resolves to `::1` first, nothing answers there, and libpq waits out the OS
   TCP timeout. The proof now sets `connect_timeout` (default 10s, `--connect-timeout`)
   and reuses one connection for the whole run. That is a fix to the harness, not to the
   product, and it is why the GREEN run above took two minutes rather than one.

---

## 8. Reproducing this

```bash
docker run -d --name mainline-crdb -p 26257:26257 cockroachdb/cockroach:v26.2.5 \
  start-single-node --insecure

python scripts/proof/gate_refusal.py \
  --dsn postgresql://root@localhost:26257/defaultdb?sslmode=disable
echo $?   # 0 == PROVEN

export MAINLINE_TEST_DSN="postgresql://root@127.0.0.1:26257/defaultdb?sslmode=disable"
python -m pytest tests/release/test_gate_refusal_proof.py -q
```

To watch it go red again on purpose, put `family` back in `0049z` — or delete any
migration between `0050` and `0130` — and run it. `chain.failures_unexplained` stops being
empty and the verdict changes. That is the property that makes this a test rather than a
demonstration.
