<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# `evidence/chain/` — recorded runs of the whole migration tree through the real runner

Each `chain-<UTC>.json` here is one execution of

```
trappoint migrate up --tree mainline --migrations verticals/mainline/db/migrations --attest each
```

against a **database created by that run**, driven by `scripts/chain/apply_chain.py`. The
script drives the runner as a subprocess, so `steps[].stdout` and `steps[].stderr` are the
runner's own bytes rather than a paraphrase of them.

Nothing in this directory is hand-written. If a number in the repository describes the
migration chain, it should be traceable to a field in one of these files.

## The record run

| | |
|---|---|
| file | `chain-20260810T062542Z.json` |
| tree | `verticals/mainline/db/migrations`, **271** files |
| result | **271 applied · 0 failed · not dirty · `complete: true`** |
| runner exit | **0** |
| attestation | head ordinal **271**, grade **strong**, 272 rows, `chain_dense: true` |
| fingerprint | `7749748562a77f98a84c7f6d5cf25ead9453494f413044133e1a4e3484cbad28` |
| cluster | CockroachDB CCL **v26.2.5**, `gc.ttlseconds` **4500** (the Cloud Basic value) |
| timings | bootstrap 133.6 s · `up --attest each` 1931.5 s · `grants apply` 139.3 s · wall 2725.0 s |
| grants | 112 statements asserted, 11 skipped, all `42P01`, 11 distinct relations |
| database | `w6_record`, created by the run and kept (`--keep`) |

`grade: strong` means the fingerprint covers schemas, types, tables **and** trigger and
routine source text — so the merge gate's own body is inside the hash. `weak` would mean
`pg_get_triggerdef`/`pg_get_functiondef` were unavailable and the claim had softened, which
is recorded in the data rather than only in prose.

---

## The distinction these files exist to hold

`docs/HONESTY.md` published **246 of 261 applied**. That number came from
`scripts/proof/gate_refusal.py`, which applies every file with **continue-on-error** and
counts how many took effect. It is a census, it says so in its own docstring, and it is
accurate about what it measured.

It is not a deployment. Through `trappoint migrate up` — forward-only, one bookkeeping row
per file, stop on first failure — the same tree applied **155 of 261** and halted at
`0121_trg_check_materialised` with `[42P01] relation "mainline_ops.outbox" does not exist`,
leaving `0121` **dirty**. Everything below file 156 had never been executed by the thing
that executes migrations in production.

The two numbers differed by 91 files. These files record the second kind only. Every one of
them carries a `prior_claims_retired` block naming both superseded numbers, so a reader who
finds an old quotation can see what replaced it.

---

## Reading a file

| field | what it is |
|---|---|
| `result.files` | `.sql` files on disk in the tree, at the moment of the run |
| `result.applied` | rows in `trappoint.schema_migration` with `state = 'applied'` |
| `result.failed` | `files - applied` |
| `result.dirty` | true if any version is `dirty` — a halted run |
| `result.complete` | `applied == files` **and** nothing dirty. The script exits non-zero unless this is true |
| `result.runner_exit_status` | the exit status of `trappoint migrate up` itself |
| `result.runner_final_line` | the last non-empty line the runner printed (stderr wins, because a refusal goes there) |
| `result.unresolved[]` | every non-applied version, with the database's own SQLSTATE and message |
| `attestation.head` | ordinal, kind, version, grade and hex fingerprint of the chain head |
| `attestation.rows` | attestation rows written — genesis + one per file under `--attest each` |
| `attestation.chain_dense` | ordinals are gap-free. They are dense **by compare-and-swap**, so a gap is not a lost row, it is a rewrite |
| `cluster.version` | `SELECT version()` from the node that took the run |
| `cluster.gc_ttlseconds` | read back from `SHOW ZONE CONFIGURATION`; pinned to **4500**, the Cloud Basic value, because the local default of 14400 is the *more permissive* of the two |
| `operation.attest` | `each` for a record run, `final` for a fast iteration |
| `operation.forced_versions` | always `0`. A `trappoint migrate force` in a build loop would make the number meaningless |
| `wall_clock_seconds` | the whole script, including database creation and read-back |
| `grants` | present when the run passed `--grants`: statements asserted, and the census of relations `GRANTS.yaml` names that no migration produces |
| `steps[]` | argv, exit status, seconds, stdout, stderr for every subprocess |
| `applied_versions[]` | the applied versions in order — the audit trail behind `result.applied` |

---

## What is *not* recorded here, on purpose

* **No continue-on-error count.** If a file fails, the run stops and the number is smaller.
  That is the point.
* **No aggregate across runs.** One file, one execution, one database.
* **Nothing about grants beyond what a real `--allow-missing` run reported.** The eleven
  relations `GRANTS.yaml` names and no migration creates are *reported, not authored*
  (producers-plan D12); the list in `grants.relations_absent` comes out of the run, not out
  of a plan.

---

## Reproducing

```
.venv/Scripts/python.exe scripts/chain/apply_chain.py --attest each --grants
```

See `scripts/chain/README.md` for the flags, the budget (25–30 minutes, and why), and what
a green line looks like. `docs/release/chain-268.md` is the release note that quotes these
files.
