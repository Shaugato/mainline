<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# The chain, through the runner a deployment uses

**Worker:** `W6` · producer-completion wave · **2026-08-10**
**Cluster:** the local single-node Docker container `mainline-crdb`,
**CockroachDB CCL v26.2.5** (x86_64-pc-linux-gnu, built 2026/07/28 18:56:00, go1.25.5)
**Interpreter:** `.venv/Scripts/python.exe`
**Evidence:** `evidence/chain/chain-20260810T062542Z.json`
**Driver:** `scripts/chain/apply_chain.py` (see `scripts/chain/README.md`)

> **On the filename.** The plan that commissioned this document called the wave
> *chain-268*, and 268 was its projection. The tree it produced holds **271** files:
> 261 before the wave, plus the seven producers and the three welds its own §1.3
> enumerates — 261 + 10 = 271, not 268. The plan's header and its allocation table
> disagreed with each other by three. **The measurement wins**; the filename is kept
> because other documents already point at it.

---

## 0 · The number, and the two numbers it replaces

| | census | **deployment** |
|---|---|---|
| driver | `scripts/proof/gate_refusal.py`'s own chain | `trappoint migrate up` |
| on a failing file | logs it and **continues** | marks the version `dirty` and **stops** |
| bookkeeping | none | `trappoint.schema_migration`, one row per file |
| attestation | none | one chained fingerprint per file (`--attest each`) |
| **before this wave** | **246 of 261** | **155 of 261** |
| **after this wave** | — | **271 of 271** |

* **246 of 261** is `evidence/gate-refusal/proof-20260809T213857Z.json#chain.applied_count`
  and again `proof-20260810T004200Z.json#chain.applied_count`. It is a *census*: how many
  files can take effect if you keep going past the ones that cannot. Its own docstring says
  so. It is the number `docs/HONESTY.md` published.
* **155 of 261** is the *deployment* number, measured by the producer-completion lead on
  2026-08-10 and transcribed in `docs/leads/producers-plan.md` §0: `trappoint migrate up`
  halted at `0121_trg_check_materialised` with
  `[42P01] relation "mainline_ops.outbox" does not exist`, leaving 155 applied, `0121`
  **dirty**, and 156 rows in `trappoint.schema_migration`. Everything below file 156 —
  105 files — had never been executed by the thing that executes migrations in production.
  **This document does not re-measure that number**, because doing so would mean deleting
  seven migration files this wave added and which W6 does not own. It is cited, with its
  source, as the claim being beaten. What W6 *did* verify independently is the arithmetic
  the claim rests on: removing this wave's ten files from the tree leaves exactly 261, and
  `0121_trg_check_materialised.sql` is index **156** in apply order among them — so a halt
  there does leave 155 clean and one dirty. (In the 271-file tree it is index 163.)
* The two differed by **91 files**, and only the smaller one described a deployment.

**The claim this document makes is the right-hand column, and nothing else:
271 of 271 files applied by `trappoint migrate up`, forward-only, from a
database created by the run, with an attestation row per file, exit status 0.**

---

## 1 · The run

```
$ .venv/Scripts/python.exe scripts/chain/apply_chain.py --attest each --grants --keep
```

which is exactly these three commands against a database it creates:

```
trappoint migrate bootstrap --dsn <fresh>
trappoint migrate up --dsn <fresh> --tree mainline \
    --migrations verticals/mainline/db/migrations --attest each
trappoint migrate grants apply --dsn <fresh> \
    --matrix verticals/mainline/db/GRANTS.yaml --allow-missing
```

Verbatim output. One note on fidelity: the program writes `·` and `—`, and the Windows
console renders both as `?`; the characters below are the ones the program emitted, not the
ones the terminal drew. Nothing else is altered and nothing is trimmed.

```
chain: 271 file(s) on disk in D:\CoackroachDBxAWS\mainline\verticals\mainline\db\migrations
chain: database w6_record (fresh; a halted run leaves a DIRTY version behind)
chain: attest=each
    cluster: CockroachDB CCL v26.2.5 (x86_64-pc-linux-gnu, built 2026/07/28 18:56:00, go1.25.5)
    gc.ttlseconds = 4500 (Cloud value 4500)
    migrate bootstrap: exit 0 in 133.6s
    migrate up --attest each: exit 0 in 1931.5s
    migrate grants apply --allow-missing: exit 0 in 139.3s
chain: KEPT database w6_record
chain: DSN postgresql://root@localhost:26257/w6_record?sslmode=disable
chain: wrote evidence/chain/chain-20260810T062542Z.json

CHAIN  files 271  applied 271  failed 0  dirty False
CHAIN  runner exit 0 · fingerprint 7749748562a77f98a84c7f6d5cf25ead9453494f413044133e1a4e3484cbad28 (grade strong, attestation ordinal 271)
CHAIN  wall clock 2725.0s
CHAIN  attestation ordinal 271 grade strong · 7749748562a77f98a84c7f6d5cf25ead9453494f413044133e1a4e3484cbad28
CHAIN  VERDICT COMPLETE — 271/271 through `trappoint migrate up`

$ echo $?
0
```

The runner's own last line, quoted from `steps[].stdout` in the evidence file:

```
fingerprint 7749748562a77f98a84c7f6d5cf25ead9453494f413044133e1a4e3484cbad28 (grade strong, attestation ordinal 271)
```

### 1.1 · What each field of the verdict means

| field | value | why it is in the verdict |
|---|---|---|
| `files` | 271 | `.sql` files on disk in `verticals/mainline/db/migrations` |
| `applied` | 271 | rows in `trappoint.schema_migration` with `state = 'applied'` — read back with SQL, not parsed out of the runner's prose |
| `failed` | 0 | `files - applied` |
| `dirty` | `false` | any version left `applying`/`dirty`. A halted forward-only run leaves one, and `up` then refuses to advance |
| `runner exit` | **0** | the exit status of `trappoint migrate up` itself |
| attestation head | ordinal 271 (272 rows), grade `strong` | genesis + one row per file. `chain_dense` = `true`: the ordinals are gap-free **by compare-and-swap**, so a gap is a rewrite and not a lost row |
| `gc.ttlseconds` | 4500 | pinned to the CockroachDB **Cloud Basic** value and read back out of `SHOW ZONE CONFIGURATION`. The local default is 14400, which is the *more permissive* of the two |
| `forced_versions` | 0 | no `trappoint migrate force` anywhere in the run. A forced version would make the number meaningless |
| wall clock | 2725.0 s | the whole script |

The script **exits non-zero** unless `applied == files` and nothing is dirty. A quoted run
is a run that passed.

### 1.2 · The same claim, from the runner instead of from the script

`--keep` left the database behind, so the deployment runner can be asked directly, with no
part of `apply_chain.py` in the path:

```
$ trappoint migrate status --dsn postgresql://root@localhost:26257/w6_record?sslmode=disable \
    --tree mainline --migrations verticals/mainline/db/migrations
tree mainline · verticals\mainline\db\migrations
  applied     271
  pending     0
  unresolved  0
  attestation head: ordinal 271 kind apply grade strong · 7749748562a77f98a84c7f6d5cf25ead9453494f413044133e1a4e3484cbad28
  chain intact (dense, and every prev_fingerprint matches its predecessor)

$ echo $?
0
```

`unresolved 0` is the one that matters: the runner is reporting that **no version is left
`applying` or `dirty`** — which is the state a halted forward-only run leaves behind, and the
state that made the old number 155. `chain intact` is the attestation ledger checking itself:
dense ordinals, and every `prev_fingerprint` equal to its predecessor's `fingerprint`.

---

## 2 · What made it possible: seven producers and three welds

The halt was one instance of one defect: **consumers written for tables nobody produced**.
`CREATE FUNCTION` on v26.2.5 does *not* resolve table references inside a PL/pgSQL body, so
`0101_fn_check_materialised` and `0140a_fn_cbm_account_guard` applied clean with their tables
absent; `CREATE TRIGGER` *does* resolve them. The census file shows it directly — every one
of its 15 failures is `42P01`, and the first two are the *triggers*, not the functions:

```
evidence/gate-refusal/proof-20260810T004200Z.json#chain.failures_attributable_to_an_unproduced_table
  0121_trg_check_materialised   42P01  relation "mainline_ops.outbox" does not exist
  0145a_trg_cbm_account_guard   42P01  …
  0163_v_fixity_coverage        42P01  …                              (15 in total)
```

That is why the tree died at `0121` and would have died again at `0145a`, and it is why a
new table must sort before the **trigger** that welds its consumer, never merely before the
function.

Seven tables were missing. The numbers were not chosen — four already-committed artefacts
had fixed each one (`requires:` headers, `GRANTS.yaml`'s `since:` keys, `ARCHITECTURE.md`
§18, `RLS-MATRIX.yaml`), and moving any would have falsified all four.

| file | relation | band | what it unblocks |
|---|---|---|---|
| `0049d_identity_assignment` | `mainline.identity_assignment` | `0049a-0049z` authored | `0140a` (fn body), `0145a_trg_cbm_account_guard` |
| `0089_agent_action` | `mainline_meas.agent_action` | `0080-0089z` authored | `0164`, `0165`, `0166` |
| `0089a_person_measure_policy` | `mainline_meas.person_measure_policy` | `0080-0089z` authored | `0089b` (`NOT NULL REFERENCES`), `0171`, `0172` |
| `0089b_standing` | `mainline_meas.standing` | `0080-0089z` authored | `0171`, `0172`, `0187`, `0187a`–`0187e` |
| `0090_patrol_run` | `mainline.patrol_run` | `0090-0099z` authored | `0163_v_fixity_coverage` |
| `0099_outbox` | `mainline_ops.outbox` | `0090-0099z` authored | `0101` (fn body), **`0121_trg_check_materialised`**, `0198x` |
| `0099a_site_register_signal` | `mainline_ops.site_register_signal` | `0090-0099z` authored | `RLS-MATRIX.yaml` `rls_forbidden`, `test_mi_rls.py` |

`mainline_meas.person_measure_policy` was invisible to the failure census that produced the
"five unproduced tables" figure: CockroachDB reports the **first** absent relation in a
statement, `standing` is named first in both `0171` and `0172`, so `person_measure_policy`
never appeared in a SQLSTATE. A census of SQLSTATEs could not have found it. A census of
*references* could, and now does — see §4.3.

### 2.1 · The three welds

| file | trigger | on |
|---|---|---|
| `0145f_trg_identity_assignment_append_only` | `append_only` | `mainline.identity_assignment` |
| `0149a_trg_agent_action_append_only` | `append_only` | `mainline_meas.agent_action` |
| `0149b_trg_person_measure_policy_append_only` | `append_only` | `mainline_meas.person_measure_policy` |

Each is welded because MI01 is cited by the very views that read the table. `0149b` is the
one that carries a whole argument rather than a convention: `notice_precedes_effect` and
`instrument_precedes_effect` are `CHECK`s, and a `CHECK` constrains a *row* — an `UPDATE`
simply produces a different row that also satisfies it. Without the weld, every policy row
is correctly ordered at the moment anyone looks at it, and no reader can distinguish one
that was ordered when written from one that was reordered afterwards.

**`mainline_ops.outbox` deliberately has no weld, and that is a decision, not an omission.**
It is one of the three allow-listed row-level-TTL tables (30 days). A `BEFORE DELETE`
refusal trigger would make the expiry job fail forever — an append-only weld on a table
whose contract is expiry is a self-inflicted permanent outage.

---

## 3 · The paired green: `producer-absent`

A lint that has never been observed red asserts nothing (PL-2). W1 captured the red over the
**261-file** tree before the producers landed:

```
evidence/producers/producer-census-before.json#before
  files              261
  produced           134
  references         586
  absent_relations   7   (outbox · identity_assignment · patrol_run · agent_action ·
                          standing · person_measure_policy · site_register_signal)
```

The same rule over the tree today — measured by W6, which is what that file's
`expected_after_the_wave.asserted_by` names:

```
$ .venv/Scripts/python.exe -c "from pathlib import Path; \
    from trappoint_migrate.producers import census; \
    c = census(Path('verticals/mainline/db/migrations')); \
    print(len(c.produced), len(c.referenced), len(c.absent), c.ok)"
141 603 0 True

$ trappoint migrate lint --root verticals/mainline/db/migrations
lint: 271 file(s) checked in verticals\mainline\db\migrations
lint: no findings — no sequence, every migration cites an invariant, and every header
      answers MI/I/COUNSEL-GATED/RATIONALE
```

Rule D runs **by default** (`--no-producers` turns it off), so the zero above includes it.
603 schema-qualified references, 141 producers, **0 absent**.

---

## 4 · The derived artefacts

### 4.1 · The lock is derived, and it is current (MR-6)

```
$ trappoint migrate lock --migrations verticals/mainline/db/migrations --write
wrote verticals\mainline\db\migrations.lock.json — 271 file(s), 107 rendered,
  164 authored, 30 counsel-gated

$ trappoint migrate lock --migrations verticals/mainline/db/migrations
verticals\mainline\db\migrations.lock.json is current
```

Write, then check with no flag. The check is the deliverable; the write is how you get
there. A hand-edited entry would be a second source of truth, which is the class of failure
the migration reconciliation of 2026-08-08 exists to end.

### 4.2 · The manifest describes the tree that deploys

`verticals/mainline/db/MIGRATIONS.md` was describing a tree that halts. It now carries a
measured §0 (counts, statement census, and the census-vs-deployment table), a §5 band table
projected from the lock, and a §6 that states the producer rule and names all seven tables.
Its command block no longer says `uv run`: `uv` is not installed on this workstation
(`docs/HONESTY.md`), and a contract whose first four commands do not run is not a contract.

### 4.3 · The grants census — reported, not authored

`GRANTS.yaml` names relations that **no migration in this tree produces**. None of them
blocks a migration: no file in the tree references one, so the chain reaches
271/271 with them absent. Authoring eleven speculative tables would be a
second domain's work smuggled into a repair wave (producers-plan D12), so they are
**reported**.

From a real `--allow-missing` run against the migrated database — not from a list:

```
D:\CoackroachDBxAWS\mainline\verticals\mainline\db\GRANTS.yaml: 112 statement(s) asserted
  skipped (object absent) [42P01] GRANT INSERT ON TABLE mainline.document_intake_finding TO agent_ingestor
  skipped (object absent) [42P01] GRANT INSERT ON TABLE mainline.observed_assertion TO agent_patroller
  skipped (object absent) [42P01] GRANT INSERT ON TABLE mainline.drift_finding TO agent_patroller
  skipped (object absent) [42P01] GRANT INSERT ON TABLE mainline.time_witness TO agent_patroller
  skipped (object absent) [42P01] GRANT INSERT ON TABLE mainline.discordance_warrant TO agent_patroller
  skipped (object absent) [42P01] GRANT INSERT ON TABLE mainline.lesson TO agent_fleet
  skipped (object absent) [42P01] GRANT INSERT, UPDATE ON TABLE mainline.propagation TO agent_fleet
  skipped (object absent) [42P01] GRANT INSERT ON TABLE mainline.merge_conflict TO agent_fleet
  skipped (object absent) [42P01] GRANT INSERT ON TABLE mainline.resolution_memory TO agent_fleet
  skipped (object absent) [42P01] GRANT INSERT ON TABLE mainline_meas.assay_outcome TO agent_assay
  skipped (object absent) [42P01] GRANT INSERT ON TABLE mainline_meas.external_attestation TO mainline_auditor
```

123 statements in the matrix: **112 asserted, 11 refused, every refusal `42P01`.**

| relation | the grant that could not be made | SQLSTATE |
|---|---|---|
| `mainline.document_intake_finding` | `GRANT INSERT ... TO agent_ingestor` | `42P01` |
| `mainline.observed_assertion` | `GRANT INSERT ... TO agent_patroller` | `42P01` |
| `mainline.drift_finding` | `GRANT INSERT ... TO agent_patroller` | `42P01` |
| `mainline.time_witness` | `GRANT INSERT ... TO agent_patroller` | `42P01` |
| `mainline.discordance_warrant` | `GRANT INSERT ... TO agent_patroller` | `42P01` |
| `mainline.lesson` | `GRANT INSERT ... TO agent_fleet` | `42P01` |
| `mainline.propagation` | `GRANT INSERT, UPDATE ... TO agent_fleet` | `42P01` |
| `mainline.merge_conflict` | `GRANT INSERT ... TO agent_fleet` | `42P01` |
| `mainline.resolution_memory` | `GRANT INSERT ... TO agent_fleet` | `42P01` |
| `mainline_meas.assay_outcome` | `GRANT INSERT ... TO agent_assay` | `42P01` |
| `mainline_meas.external_attestation` | `GRANT INSERT ... TO mainline_auditor` | `42P01` |

Eleven relations, eleven statements, one SQLSTATE. Every one of them is a **write** grant to
an agent role, which is the shape of the gap: the roles and the schema exist, the tables the
agents would write into do not.

The full skipped statements, each with the SQLSTATE the database returned, are in
`evidence/chain/chain-20260810T062542Z.json#grants.skipped_object_absent`.

`--allow-missing` is legitimate while a tree is mid-build and is a **defect on a finished
cluster**. Recording the census rather than discarding it is what keeps that distinction
alive.

---

## 5 · The budget, measured

`--attest each` recomputes the live schema fingerprint after **every** statement — and
"recompute" means twice, compared, because a fingerprint that flickers is worse than none.
Measured on this node, on this day:

| operation | files | seconds | note |
|---|--:|--:|---|
| the continue-on-error **census** | 261 | 46.9 | `evidence/gate-refusal/proof-20260810T004200Z.json#chain.seconds` — no bookkeeping, no lease, no fingerprint |
| `migrate up --attest final` | 271 | 334.5 | one attestation for the whole run |
| `migrate up --attest each` | 271 | **1931.5** | **the record run**, 7.1 s/file |
| `migrate bootstrap` | — | 133.6 | four statements and their schema jobs |
| `grants apply --allow-missing` | — | 139.3 | 123 statements, one transaction each, deliberately |
| the whole script, wall clock | 271 | 2725.0 | including `CREATE DATABASE`, the zone pin and the read-back |

`--attest each` is **~6× `--attest final`** and **~41× the census** over the same 271 files.
That ratio is the price of a per-file attestation chain — and it is a large part of why the
census number was the one that got quoted.

The per-file cost is not stable, and it tracks **how busy the shared local node is** rather
than how big the tree is: mid-wave, a *two-file* scratch tree cost 147 s for its two files
while three other jobs held databases on the same container. Iterate with `--attest final`;
take the record with `--attest each`; budget half an hour and do not be surprised by an hour.

---

## 6 · What is still not true

* **Nothing here has been run against CockroachDB Cloud.** Every number on this page comes
  from the local v26.2.5 container. `gc.ttlseconds` is pinned to the Cloud value so the
  local node is the stricter of the two, which is a mitigation and not a substitute.
* **The eleven relations in §4.3 remain unproduced**, by decision. Any consumer written for
  one of them will be refused by `producer-absent` at lint time before it can halt a chain —
  which is the ratchet doing its job, not a gap being closed.
* **This document does not re-measure 155/261.** It cites it, and verifies only the
  arithmetic underneath it. Re-measuring would mean deleting seven files W6 does not own.
* The record run's database is **kept** (`--keep`) so another job can inherit it; it is a
  scratch database on a local node and it is not a deployment.
* **Grants were asserted with `--allow-missing`.** A finished cluster should be able to run
  `grants apply` with no flag and get 123 of 123. It cannot today, and §4.3 is why. That is
  a known-red, not a rounding.
* **`docs/HONESTY.md` still published 246/261 at the time of writing.** Re-basing it is
  W10's file and W10's job; this page is one of the artefacts it will cite.

---

## 7 · Reproducing, in one command

```
.venv/Scripts/python.exe scripts/chain/apply_chain.py --attest each --grants
```

Green is the line

```
CHAIN  VERDICT COMPLETE — 271/271 through `trappoint migrate up`
```

and exit status 0. Anything less prints `VERDICT INCOMPLETE`, names every unresolved version
with its SQLSTATE, and exits 1.

`scripts/chain/README.md` documents the flags and the budget.
`evidence/chain/README.md` documents every field of the JSON.
