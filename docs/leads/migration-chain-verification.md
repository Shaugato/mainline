<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# MIGRATION CHAIN VERIFICATION — empirical result

**Run:** 2026-08-08
**Verifier:** migration chain verifier (last check before the build resumes)
**Tree:** `verticals/mainline/db/migrations` — **105 files**
**Ruling under test:** `docs/leads/migration-reconciliation.md` (MR-1 … MR-8, MRR-1 … MRR-7)
**Cluster:** local Docker node `mainline-crdb`, **CockroachDB CCL v26.2.5** (x86_64-pc-linux-gnu,
built 2026/07/28), `postgresql://root@localhost:26257/…?sslmode=disable`, insecure, single replica.

---

## VERDICT IN ONE LINE

> **Structurally GREEN — every MR-5/MR-6 check passes, all 105 files, zero findings.
> The full chain does NOT apply: it stops at file 80 of 105, `0077_unwitnessed_debt.sql`,
> `[42P01] relation "mainline.permit" does not exist`.
> The stop is caused by PENDING kernel work, not by the reconciliation. 103 of 105 files apply
> when the two blocked files are skipped, and the only two blockers are forward references to
> `mainline.permit` (0050) and `mainline.blocking_check` (0058) — both allocated to kernel
> workers that have not yet been dispatched, and both correctly ordered *before* their consumers.**

**The kernel gate does not exist in this tree.** `permit`, `blocking_check`, `merge_record`,
`refusal_ledger`, `disposition`, `permit_event` and every merge-gate trigger are absent. A merge-gate
refusal therefore **cannot be proven today** and none is claimed below. What *is* proven, empirically,
is that the refusal machinery that IS on disk refuses and admits correctly (§4).

---

## 1. THE COMMAND SEQUENCE

Everything below was executed against the local node. Times are wall-clock, measured.

```bash
# --- 0. platform ---
docker ps                            # mainline-crdb  cockroachdb/cockroach:v26.2.5  :26257
docker exec mainline-crdb cockroach sql --insecure -e "SELECT version();"
# -> CockroachDB CCL v26.2.5 (x86_64-pc-linux-gnu, built 2026/07/28 18:56:00, go1.25.5)

# --- 1. structural: the runner's own code, not a re-implementation ---
export PYTHONPATH=packages/trappoint-migrate/src
python - <<'PY'
from pathlib import Path
from trappoint_migrate import discovery, lint
root = Path('verticals/mainline/db/migrations')
ms = discovery.discover(root)                 # -> 105 migrations, 105 unique versions
print(lint.find_allocation(root))             # -> verticals/mainline/db/migrations.allocation.toml, 33 bands
rep = lint.lint_paths([root])                 # -> ok=True, files_checked=105, findings=0
PY

export PYTHONPATH=packages/trappoint-sql/src
python -c "from pathlib import Path; from trappoint_sql.render import stem_collisions; \
print(stem_collisions(Path('verticals/mainline/db/migrations')))"      # -> []

# --- 2. fresh database + the stricter of the two GC settings ---
docker exec mainline-crdb cockroach sql --insecure \
  -e "DROP DATABASE IF EXISTS chain_verify CASCADE; CREATE DATABASE chain_verify;"
# ALTER RANGE default CONFIGURE ZONE USING gc.ttlseconds = 4500   (§8 of the ruling)

# --- 3. the whole chain, in order, through the real runner ---
export LOCAL_DSN="postgresql://root@localhost:26257/chain_verify?sslmode=disable"
export PYTHONPATH=packages/trappoint-migrate/src
python -m trappoint_migrate bootstrap --dsn "$LOCAL_DSN"
python -m trappoint_migrate up        --dsn "$LOCAL_DSN" \
       --migrations verticals/mainline/db/migrations
python -m trappoint_migrate status    --dsn "$LOCAL_DSN" \
       --migrations verticals/mainline/db/migrations

# --- 4. survey run: apply all 105, continue past failure, to enumerate the whole break set ---
#     (psycopg3 3.3.4, autocommit, one file = one execute; CREATE DATABASE chain_survey)

# --- 5. refusal probes against the applied tree (chain_survey)
```

Two commands from ruling §8 were **not** run and are not claimed:
`trappoint render --binding … --check` for either binding. They are a render-engine assertion, not a
chain assertion, and this report does not speak to them. `stem_collisions()` — the function MR-6
lock 3 promotes into that check — **was** run directly and is empty.

---

## 2. STRUCTURAL CHECKS

| # | Check | Result | Evidence |
|---|---|---|---|
| S1 | **Exactly one filename convention** — `^\d{4}[a-z]?_[a-z0-9_]+\.sql$` | **PASS** | 105/105 match. **Zero `.up.sql` files remain** (was 49). Zero second-dot filenames (was 2). |
| S2 | **No duplicate version stems** | **PASS** | `discover()` returns 105 migrations with **105 unique versions**. The 7 duplicate stems `0010`–`0016` are gone. `stem_collisions()` → `[]`. |
| S2b | No two files share a bare number | **PASS** | The 13 repeated leading-4-digit groups (`0006`×9, `0007`×5, `0008`×5, `0009`×7, `0017`, `0018`, `0020`, `0029`, `0049`, `0072`, `0086`, `0114`, `0138`) are all **letter-suffix families under one owner** — the legal MR-5 use. |
| S3 | **REUSE SPDX header on every file** | **PASS** | 105/105 carry both `SPDX-FileCopyrightText` and `SPDX-License-Identifier` in the first 4 KiB. |
| S3b | The four linted keys `MI: / I: / COUNSEL-GATED: / RATIONALE:` | **PASS** | 105/105. |
| S4 | **No banned constructs** — `CREATE SEQUENCE`, `nextval(`, `SERIAL`, `unique_rowid()` | **PASS** | Zero hits in executable text (comments and string/dollar literals stripped; routine bodies *kept*, so a banned call inside PL/pgSQL would still be caught). The 4 raw grep hits in `0073_ledger_leaf.sql` and `0079_sequencer_lease.sql` are the **ban being restated in a header comment**, not a use. |
| S5 | **Exactly one top-level statement per file** | **PASS** | 105/105 after routine bodies are collapsed. The five §0 lint failures are resolved: `0086`→`0086`+`0086a`, `0114`→`0114`+`0114a`, `0138`→`0138`+`0138a`, `0139`→`0110`+`0139`, `0211`→`0140`+`0145`. |
| S6 | Mode census | **PASS** | **45 rendered / 60 authored.** 44→45 rendered is exactly MRR-3's predicted "one added file": `0009f_revoke_create_public_schema.sql`. |
| S7 | **`migrations.lock.json` agrees with disk** | **PASS** | 105 entries; **0 only-on-disk, 0 only-in-lock, 0 sha256 mismatches**. |
| S8 | **MR-6 lock 2(b): mode matches the band's declared mode** | **PASS** | 0 violations across 105 files against the 33 bands in `migrations.allocation.toml`. |
| S9 | `trappoint migrate lint` (the authority, auto-discovering the allocation) | **PASS** | `ok=True`, `files_checked=105`, `findings=0`. |
| S10 | `discover()` does not refuse the directory | **PASS** | Returns 105; the two `.fallback.sql` files that made the whole tree undiscoverable are now in `verticals/mainline/db/ext/vector_fallback/` and out of the apply path. |
| S11 | **Gaps that imply a lost file** | **PASS (no lost files)** | Every gap resolves to a band whose owner has not yet delivered, or to a deliberately empty slot. Enumerated in §5. **No number is missing whose file existed before the reconciliation.** |

### 2.1 The four MR-6 locks were made to fire

A green lint is only evidence if the lint can go red. Four synthetic violations were planted in a
throwaway tree and linted against the real allocation:

| Planted file | Rule that fired | Detail |
|---|---|---|
| `0019_retention_class.up.sql` | `up-sql-suffix` | ".up.sql names a down counterpart that is illegal by construction (MR-5)" |
| `0020_adm_decision_class.variant.sql` | `filename-convention` | second dot; **`discover()` additionally raised `MigrationTreeInvalid` on the whole directory** — the §0 failure mode, reproduced on demand |
| `0019a_person_…sql` (rendered banner in an authored band) | `allocation-mode` | "carries the `@rendered-by` banner but sits in band 0019-0020z … mode authored" |
| `0201_v_out_of_band.sql` | `allocation-unallocated` | "sits in band 0200-9999z, owner UNALLOCATED … No file may use these numbers" |

All four are silent on the real tree. **The guard asserts something.**

### 2.2 Semantics the ruling said must survive — verified present

| §5.1 requirement | Verified |
|---|---|
| `REVOKE CREATE ON SCHEMA public FROM public` (the unique semantic of the deleted `0008_…up.sql`) | `0009f_revoke_create_public_schema.sql`, exactly that one statement |
| `clearance_legal`: `policy_version_not_blank`, `approved_by_sub_not_blank` merged into the template | present in `0018a_clearance_legal.sql` |
| `person`: `signer_sub_stated`, `identity_source_stated` merged in; rendered `person_digest_sized` kept | all three present in `0021_person.sql` |
| `signing_credential`: `signer_sub_stated` merged in; rendered `credential_revocation_reasoned` kept | both present in `0022_signing_credential.sql` |
| `subject_transition` 18-row lattice seed | **18 rows** in the applied database |
| `clearance_legal` 21-row seed with three deliberately absent cells | **21 rows** in the applied database |
| substrate constraint names are the exhibit | `pk_subject_transition`, `subject_transition_kind_known`, `pk_clearance_legal`, `pk_person`, `pk_signing_credential` — all present |

---

## 3. FULL-CHAIN APPLY — **FAIL**

### 3.1 Through the real runner

```
$ python -m trappoint_migrate bootstrap --dsn $LOCAL_DSN
bootstrapped: schema, schema_migration, schema_lock, schema_attestation, genesis attestation

$ python -m trappoint_migrate up --dsn $LOCAL_DSN --migrations verticals/mainline/db/migrations
trappoint migrate: REFUSED: 0077_unwitnessed_debt: [42P01] relation "mainline.permit" does not exist

$ python -m trappoint_migrate status --dsn $LOCAL_DSN --migrations verticals/mainline/db/migrations
tree default · verticals\mainline\db\migrations
  applied     79
  pending     25
  unresolved  1
    ! 0077_unwitnessed_debt [dirty] 42P01 relation "mainline.permit" does not exist
  attestation head: ordinal 79 kind apply grade strong · 04a98355da8159075bbf6d71b0cbf6027b6a14141a0c8bd6723a9bc13ebd5c6e
  chain intact (dense, and every prev_fingerprint matches its predecessor)
```

### 3.2 The first failure, precisely

| Field | Value |
|---|---|
| **File** | `verticals/mainline/db/migrations/0077_unwitnessed_debt.sql` (position **80 of 105**) |
| **Statement** | `CREATE TABLE mainline.unwitnessed_debt (…)` — the file's single top-level statement |
| **Offending clause** | line 91: `CONSTRAINT fk_permit FOREIGN KEY (permit_id) REFERENCES mainline.permit (permit_id)` |
| **SQLSTATE** | `42P01` |
| **Message** | `relation "mainline.permit" does not exist` |
| **Cause** | `mainline.permit` is allocated to **`0050`, mode RENDERED, owner kernel `subject-and-pin`** — a worker that has not been dispatched. |
| **Is this an ordering bug?** | **No.** `0050 < 0077`. The dependency is correctly *ahead* of its consumer; the file for it has simply not been written yet. |
| **Runner state** | `0077` marked **dirty**; 79 applied; attestation chain dense and intact through ordinal 79. The runner refused to advance, which is the designed behaviour. |

An independent apply (psycopg3, one file per `execute`, same lexicographic order) reproduced the
identical stop: **79 applied in 19.19 s**, then `0077` → `42P01`.

### 3.3 Survey run — every failure in the tree, not just the first

Applying all 105 into a second fresh database and continuing past each failure:

```
ok 103   failed 2   elapsed 21.43 s
0077_unwitnessed_debt.sql | 42P01 | relation "mainline.permit" does not exist
0137_trg_bonded_sev5.sql  | 42P01 | relation "mainline.blocking_check" does not exist
```

**103 of 105 files apply cleanly.** A static cross-reference of all 105 files against the 18 kernel
objects MR-2 lists as substrate finds **exactly these two references and no others**:

| File | Kernel object referenced | Allocated to | Order correct? |
|---|---|---|---|
| `0077_unwitnessed_debt.sql` | `mainline.permit` | `0050`, RENDERED, kernel `subject-and-pin` | yes (0050 < 0077) |
| `0137_trg_bonded_sev5.sql` | `mainline.blocking_check` | `0058`, RENDERED, kernel `obligation-and-clearance` | yes (0058 < 0137) |

`0137` is `CREATE TRIGGER bonded_sev5 AFTER INSERT ON mainline.blocking_check …`. Its function
`0113_fn_bonded_sev5` applies fine — a PL/pgSQL body is not resolved at `CREATE FUNCTION` time; only
the trigger's target table must exist.

**Both blockers disappear the moment the two pending kernel workers land. Neither is caused by the
reconciliation and neither requires a change to any file now on disk.**

### 3.4 Resulting database (survey run, 103 files)

47 tables across `mainline`, `mainline_meas`, `mainline_audit`, `mainline_qa`, `mainline_ops`;
6 routines; 5 triggers.

---

## 4. DOES THE GATE STILL REFUSE?

### 4.1 The kernel gate is NOT PRESENT — stated plainly, not worked around

Queried against the applied database, `information_schema.tables` where `table_schema='mainline'`:

| Object | Present? | Allocated to |
|---|---|---|
| `permit`, `change_request`, `permit_clause`, `cr_clause` | **absent** | `0050`–`0053` kernel `subject-and-pin` (pending) |
| `blocking_check`, `permit_event`, `cr_event`, `exposure_receipt`, `exposure_line`, `receipt_expiry`, `defeater_option` | **absent** | `0058`–`0064` kernel `obligation-and-clearance` (pending) |
| `disposition`, `disposition_citation`, `override_ledger` | **absent** | `0066`–`0068` kernel `obligation-and-clearance` (pending) |
| `merge_record`, `refusal_ledger` | **absent** | `0071`, `0071c` kernel `subject-and-pin` / `quickrefuse` (pending) |

Triggers in the whole database: `candidate_project`, `cue_prefix_project_coarse`,
`cue_prefix_project_embedding`, `recall_policy_anchored`, `z_delta_witness_required` — **five, all
recall/algorithms.** `fn_permit_merge_gate`, `trg_permit_merge_gate`, `fn_explain_refusal`,
`fn_refusal_ledger_guard` and the nine projection triggers **do not exist**.

> **Therefore: the merge-gate refusal (MI02–MI08, the `permit_merge_gate` SQLSTATE) cannot be
> exercised in this tree today, and this report claims no result for it.** Any green tick against
> "the gate refuses" before `subject-and-pin`, `obligation-and-clearance`, `projection-triggers`,
> `merge-gate-and-core` and `quickrefuse` have landed would be fabricated.

### 4.2 What the refusal machinery that IS on disk actually does — measured

Seven writes were attempted against the applied database. Every one behaved as specified.

| # | Write attempted | Expected | **Observed** | SQLSTATE | Constraint / message |
|---|---|---|---|---|---|
| R1 | `INSERT mainline.person` with `signer_sub = ''` (a §5.1 semantic merged **into the template**) | refuse | **REFUSED** | `23514` | **`signer_sub_stated`** — `failed to satisfy CHECK constraint (signer_sub != '')` |
| R2 | `INSERT mainline.clause_version` with `control_delta='weaken'`, `delta_basis='lattice'`, **no witness** | refuse | **REFUSED** | `P0001` | `MAINLINE: a lattice weakening must carry its minimal witness set` (trigger `z_delta_witness_required` → `mainline.fn_delta_witness_guard`) |
| R3 | *control* — same insert, `control_delta='restate'` | **accept** | **ACCEPTED** | — | the guard is not a blanket refusal |
| R4 | *control* — `weaken`/`lattice` **with** a minimal `delta_witness` row | **accept** | **ACCEPTED** | — | the guard admits exactly what it should |
| R5 | `INSERT mainline_meas.recall_run` citing an **unanchored** policy | refuse | **REFUSED** | `P0001` | `MAINLINE: recall policy is not anchored — a run may not cite an unanchored τ` (trigger `recall_policy_anchored`) |
| R6 | `'obliterate'::mainline.control_delta` | refuse | **REFUSED** | `22P02` | `invalid input value for enum control_delta: "obliterate"` — the rendered enum is closed |
| R7 | `clause_version.sev_max = 9` | refuse | **REFUSED** | `23514` | **`sev_range`** — `failed to satisfy CHECK constraint (sev_max BETWEEN 0 AND 5)` |

R1 is the load-bearing one for the ruling: it is a constraint the **authored** file carried, which
MR-1 required to be merged **into the template** before the authored twin was deleted. It survived
the merge, it is named (DM-10), and it refuses with its name in the diagnostic — i.e. the courtroom
exhibit is intact.

R2/R3/R4 together are the strongest available substitute for a gate proof: a refusal, and two
controls showing the refusal is discriminating rather than universal.

---

## 5. WHAT REMAINS BROKEN OR PENDING

### 5.1 BROKEN — blocks `trappoint migrate up` today (2)

| # | Item | Why | Clears when |
|---|---|---|---|
| B1 | `0077_unwitnessed_debt.sql` — `42P01 relation "mainline.permit" does not exist` | FK `fk_permit → mainline.permit` | kernel `subject-and-pin` renders `0050_permit.sql` |
| B2 | `0137_trg_bonded_sev5.sql` — `42P01 relation "mainline.blocking_check" does not exist` | `CREATE TRIGGER … ON mainline.blocking_check` | kernel `obligation-and-clearance` renders `0058_blocking_check.sql` |

**Neither is a defect in the reconciliation and neither needs an edit to any existing file.**

### 5.2 PENDING — allocated, owned, not yet written

| Band | Owner | Mode | Objects |
|---|---|---|---|
| `0037`–`0039` | datamodel `dm-blame` | authored | `blame_edge`, `clause_blame_closure`, `clause_blame_current` — declared in `workers.json`, never written. **The `dm-blame` worker delivered 0032–0036 only.** |
| `0050`–`0053` | kernel `subject-and-pin` | **rendered** | `permit`, `change_request`, `permit_clause`, `cr_clause` — **blocks B1** |
| `0054`–`0057` | datamodel ex-`dm-gate` | authored | `asset_edge`, `permit_boundary`, `permit_slice`, `boundary_certificate` |
| `0058`–`0064` | kernel `obligation-and-clearance` | **rendered** | `blocking_check` (+`0058a`/`0058b`), `permit_event`, `cr_event`, `exposure_receipt`, `exposure_line`, `receipt_expiry`, `defeater_option` — **blocks B2** |
| `0065` | datamodel ex-`dm-gate` | authored | `mechanism_predicate`, `predicate_revocation` |
| `0066`–`0068` | kernel `obligation-and-clearance` | **rendered** | `disposition` (+`0066a`), `disposition_citation`, `override_ledger` (G0-gated) |
| `0069`–`0070` | datamodel ex-`dm-disposition` | authored | `carried_disposition`, `carried_disposition_use` (G0-gated) |
| `0071` | kernel `subject-and-pin` + `quickrefuse` | **rendered** | `merge_record`, `epoch_pin_permit`, `epoch_pin_cr`, `refusal_ledger`, its index |
| `0090`–`0099` | datamodel `dm-periphery` | authored | fixity, fleet, governance, frontier, contradiction pair, `mainline_ops.*` |
| `0100`–`0109` | kernel `projection-triggers` | **rendered** | the ten projection functions |
| `0115`–`0119` | kernel `merge-gate-and-core` | **rendered** | `fn_permit_merge_gate`, `fn_cr_merge_gate`, `proc_merge_permit`, `proc_merge_change_request`, `fn_ledger_cas_append` |
| `0119a`–`0119b` | kernel `quickrefuse` | **rendered** | `fn_explain_refusal`, `fn_refusal_ledger_guard` |
| `0120`–`0129` | kernel `projection-triggers` | **rendered** | the nine projection triggers |
| `0130`–`0133` | kernel `merge-gate-and-core` + `quickrefuse` | **rendered** | `trg_permit_merge_gate`, `trg_cr_merge_gate`, `trg_refusal_ledger_append_only` |
| `0141`–`0144`, `0146`–`0149` | datamodel `dm-functions-triggers` | authored | vertical functions and triggers beyond the two algorithms files |
| `0151`–`0154` | algorithms | authored | remaining `mainline.*` business views |
| `0155`–`0199` | datamodel `dm-views-rls` | authored | `mainline_audit` views, `mainline_qa` views, RLS policies, and `0199` `ALTER TABLE exposure_receipt ADD CONSTRAINT fk_silence` |

Deliberately empty, **not** a lost file: `0089` (recall band tail unused), `0111` (recall declared
four objects for five numbers; MR-7 fixed `0112`–`0114` because they were already on disk and
correct), and the bare `0001` / `0017` / `0018` (the templates emit `0001a`, `0017a/b`, `0018a/b`).

### 5.3 Open items that are not chain failures

| # | Item | Status |
|---|---|---|
| O1 | `MIGRATION_SUFFIXES` in both `discovery.py` and `lint.py` is still `('.sql', '.up.sql')`. MR-5 says `.up.sql` "is removed … the moment the renames land." The renames **have** landed (0 `.up.sql` on disk) but the tolerance constant has not been withdrawn. | Harmless today — lint rule `up-sql-suffix` fires on any `.up.sql` regardless, so the tolerance cannot be used silently. Withdrawing the constant is the clean close of MRR-4. |
| O2 | `trappoint render --binding … --check` was **not** executed for either binding. | Not run; not claimed. The chain-side half of that lock, `stem_collisions()`, is empty. |
| O3 | The dirty `0077` row is left in `chain_verify.trappoint.schema_migration` as the evidence for this report. | Intentional. Resolve with `trappoint migrate force` under a named incident, or drop the database. |

---

## 6. WHAT WOULD TURN THIS REPORT GREEN

1. Dispatch kernel `subject-and-pin` (`0050`–`0053`, `0071`–`0071b`) → clears **B1**.
2. Dispatch kernel `obligation-and-clearance` (`0058`–`0064`, `0066`–`0068`) → clears **B2**.
3. Re-run §1 step 3 verbatim against a fresh `chain_verify`; expect `applied 105+ / pending 0 / unresolved 0`.
4. Only then is a merge-gate refusal provable. The probe to write at that point is a
   `proc_merge_permit` call against a subject with an open `blocking_check` and no `disposition`,
   asserting the SQLSTATE **and** the constraint/trigger name — the same shape as R1/R2 above.

---

*The reconciliation did what it said it would. One convention, 105 files, one owner per number,
zero duplicate stems, zero banned constructs, a lint that fires on demand and is silent on the tree,
and 103 of 105 files applying against v26.2.5 in 21 seconds. The chain does not yet reach its end —
because five kernel workers have not been dispatched, and the two files that stop it are the two
that reach forward into their unwritten output. That is a build in progress, reported as one.*
