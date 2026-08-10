<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# `scripts/chain/` — the whole migration tree, through the runner a deployment uses

One command, one number, and a JSON file that says how it was obtained.

```
.venv/Scripts/python.exe scripts/chain/apply_chain.py
```

That is the command. It took **2725 s — 45 minutes** on 2026-08-10 and it is supposed to be
slow; see *Budget* below.

---

## What a green line looks like

The tail of the record run of 2026-08-10, verbatim (`evidence/chain/chain-20260810T062542Z.json`):

```
    migrate bootstrap: exit 0 in 133.6s
    migrate up --attest each: exit 0 in 1931.5s
    migrate grants apply --allow-missing: exit 0 in 139.3s
chain: wrote evidence/chain/chain-20260810T062542Z.json

CHAIN  files 271  applied 271  failed 0  dirty False
CHAIN  runner exit 0 · fingerprint 7749748562a77f98a84c7f6d5cf25ead9453494f413044133e1a4e3484cbad28 (grade strong, attestation ordinal 271)
CHAIN  wall clock 2725.0s
CHAIN  attestation ordinal 271 grade strong · 7749748562a77f98a84c7f6d5cf25ead9453494f413044133e1a4e3484cbad28
CHAIN  VERDICT COMPLETE — 271/271 through `trappoint migrate up`

$ echo $?
0
```

`applied` must equal `files`, `failed` must be `0`, `dirty` must be `False`, and the exit
status must be `0`. The script asserts all four itself — it exits **1** on anything less, so
a run that is quoted from is a run that passed. A red run prints
`VERDICT INCOMPLETE` and then one line per unresolved version, with its SQLSTATE.

`grade strong` means the fingerprint covers schemas, types, tables, **triggers and
routines** — the merge gate's own source text is inside the hash. `weak` would mean
`pg_get_triggerdef`/`pg_get_functiondef` were unavailable and the claim had softened; the
grade is stored so that softening is visible in the data and not only in the prose.

---

## Why this script exists, and what it refuses to be confused with

Two numbers were both being called "the chain", and they measure different operations.

| | census | **deployment** |
|---|---|---|
| driver | `scripts/proof/gate_refusal.py`'s own chain | `trappoint migrate up` |
| on a failing file | logs it and **continues** | marks the version `dirty` and **stops** |
| bookkeeping | none | `trappoint.schema_migration`, one row per file |
| attestation | none | one chained fingerprint row per file (`--attest each`) |
| what it answers | "how many of these files can take effect?" | "does this tree deploy?" |
| published, 2026-08-09 | **246 of 261** | — |
| measured, 2026-08-10, before this wave | — | **155 of 261**, halted at `0121_trg_check_materialised` `[42P01] relation "mainline_ops.outbox" does not exist` |
| measured, 2026-08-10, **after** this wave | — | **271 of 271**, exit 0 (`evidence/chain/chain-20260810T062542Z.json`) |

Neither number is dishonest about what it measured. Only one of them is a deployment, and
before this wave it was 91 files more pessimistic. This script measures **only** the
deployment, and it drives the real runner as a **subprocess** so that what it records is the
runner's own exit status and the runner's own bytes — not a reimplementation that could
quietly disagree with the thing production runs.

The evidence file says so in its own `$comment`, and carries a `prior_claims_retired` block
naming both superseded numbers.

---

## What one run does

1. **Creates a database.** Uniquely named, `chain_<utc>_<rand>`, never reused. A halted
   forward-only run leaves its version `dirty` and `up` refuses to advance past it; the
   clean recovery is a fresh database, **never** `trappoint migrate force`, which exists for
   a named incident on a cluster you cannot recreate.
2. **Pins `gc.ttlseconds = 4500`** on that database — the CockroachDB Cloud Basic value.
   The local node defaults to `14400`, which is *more permissive*: an `AS OF SYSTEM TIME`
   query reaching four hours back succeeds locally and fails on Cloud. Pinning down makes
   the local node the stricter of the two. The value is read back out of
   `SHOW ZONE CONFIGURATION` and recorded, so the claim is measured rather than asserted.
3. **`trappoint migrate bootstrap`** — `trappoint.schema_migration`, `schema_lock`,
   `schema_attestation`, and the genesis attestation row.
4. **`trappoint migrate up --tree mainline --migrations verticals/mainline/db/migrations
   --attest each`** — forward-only, stdout and stderr captured verbatim.
5. **Reads the bookkeeping back with SQL**: how many rows, which versions, whether any is
   `dirty`, the attestation head (ordinal, grade, fingerprint), and whether the attestation
   ordinals are **dense**. Density is the whole claim of that ledger — ordinals are gap-free
   by compare-and-swap, so a missing ordinal is not a lost row, it is a rewrite.
6. **Writes `evidence/chain/chain-<utc>.json`** and drops the database (unless `--keep`).

---

## Options

| flag | what it is for |
|---|---|
| `--attest final` | one attestation for the whole run instead of one per file. **Iteration only** — measured ~6× faster, and it is not the record run. |
| `--keep` | do not drop the database; print its DSN so another job can inherit a migrated cluster instead of paying the 25 minutes again |
| `--grants` | additionally run `trappoint migrate grants apply --allow-missing` against the migrated database and record the census of relations `GRANTS.yaml` names that no migration creates |
| `--no-evidence` | do not write the JSON, so a smoke run cannot later be quoted as a record |
| `--dsn` | the admin DSN (default `$LOCAL_DSN`, else the local node) |
| `--database` | force the database name instead of generating one |
| `--migrations`, `--tree` | point at a different tree |

---

## Budget

`--attest each` recomputes a stable schema fingerprint after **every** statement — and
"stable" means it computes it twice and refuses if the two disagree. That dominates the run.
Measured on the local v26.2.5 node, same tree, same day:

| what | files | seconds | s/file |
|---|--:|--:|--:|
| the continue-on-error **census** (`scripts/proof/gate_refusal.py`) | 261 | **47** | 0.18 |
| `migrate up --attest final` | 271 | **334** | 1.2 |
| **`migrate up --attest each`** — the record run | 271 | **1931** | **7.1** |
| `migrate bootstrap` alone | — | **134** | — |
| `grants apply --allow-missing` (123 statements) | — | **139** | — |
| the whole script, wall clock | 271 | **2725** | — |

So `--attest each` is **~6× `--attest final`** and **~41× the census**, and all three are
measuring the same 271 files. That ratio is the price of a per-file attestation chain, and
it is the reason the census number was the one being quoted.

The per-file cost is not stable, because it tracks **how busy the shared local node is**
rather than how big this tree is: during this wave a *two-file* scratch tree cost 147 s for
its two files while three other jobs held databases on the same container. Budget half an
hour; do not be surprised by an hour. The wall clock is recorded, never asserted.

---

## Reading the evidence file

```jsonc
{
  "result": {
    "files": 271, "applied": 271, "failed": 0, "dirty": false,
    "complete": true,
    "runner_exit_status": 0,
    "runner_final_line": "fingerprint 7749…ad28 (grade strong, attestation ordinal 271)"
  },
  "attestation": { "head": { "ordinal": 271, "grade": "strong", … },
                   "rows": 272, "chain_dense": true },
  "cluster":  { "version": "CockroachDB CCL v26.2.5 …", "gc_ttlseconds": 4500 },
  "operation": { "forward_only": true, "continue_on_error": false, "forced_versions": 0 },
  "grants":   { "statements_asserted": 112, "statements_skipped": 11,
                "sqlstates": { "42P01": 11 }, "relations_absent": [ … 11 … ] },
  "steps": [ { "argv": […], "exit_status": 0, "stdout": "…", "stderr": "…" } ]
}
```

`steps[].stdout` and `steps[].stderr` are the runner's own bytes. Anything this repository
quotes about the chain should be traceable to one of them.

---

## If it comes back red

The script prints every unresolved version with its SQLSTATE, and the same rows are in
`result.unresolved` with the database's own message. Then:

* `[42P01] relation "x.y" does not exist` — a **consumer without a producer**. The tree has
  a trigger, view or policy for a table nobody wrote a `CREATE TABLE` for. This is the class
  of defect `trappoint migrate lint`'s `producer-absent` rule now refuses at lint time; if
  it reached the runner, the lint was bypassed.
* `DirtyMigration` on a *second* run against the same database — expected, and the reason
  this script never reuses one.
* A failing file is **its author's** to fix. Report the filename, the SQLSTATE and the
  runner's exact message; do not edit a migration to make this script green.

---

## Related

* `evidence/chain/README.md` — what the recorded runs are and how to read them
* `docs/release/chain-268.md` — the release note: the before number, the after number, the
  commands, and the welds
* `verticals/mainline/db/MIGRATIONS.md` — the migration contract and the band table
