<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: FSL-1.1-ALv2
-->

# The migration contract

Everything a person needs in order to add a statement to this schema without breaking
somebody else's, in the order they will need it. Every rule below is enforced by a
command; none of them is enforced by this document. Where the two disagree, run the
command — and then fix this document, because a contract that has drifted from its
enforcement is worse than no contract.

```
trappoint migrate lint --root verticals/mainline/db/migrations   # naming, allocation, sequences, headers, producers
trappoint migrate lock --migrations verticals/mainline/db/migrations   # the manifest is derived and current
trappoint migrate verify --offline
python scripts/mi_ratchet.py check                               # the invariant catalogue is committed and current
```

> **On `uv run`.** CI invokes these as `uv run trappoint …`. `uv` is **not installed on the
> founder's workstation** (`docs/HONESTY.md`), so the spellings above are the ones that work
> today: the console script from `.venv/Scripts/`. Both reach the same `main`.

---

## 0 · The tree, measured

Every number in this section is read off the tree or off a recorded run. Nothing here is a
target.

| | | source |
|---|---|---|
| files in the tree | **271** | `migrations.lock.json#counts.files` |
| rendered | 107 | `#counts.rendered` |
| authored | 164 | `#counts.authored` |
| counsel-gated | 30 | `#counts.counsel_gated` |
| counsel-gated but undeclared | **0** | `#counsel_gated_undeclared` |
| bands occupied (of 33 declared) | 32 | `#counts.bands_occupied` |
| **applied through `trappoint migrate up`** | **271 / 271**, exit 0 | `evidence/chain/chain-20260810T062542Z.json#result` |
| attestation rows written | 272 (genesis + one per file) | `#attestation.rows`, `chain_dense: true` |
| lint findings, incl. `producer-absent` | **0** | `trappoint migrate lint --root verticals/mainline/db/migrations` |
| relations with a consumer and no producer | **0** of 603 references | `trappoint_migrate.producers.census` |

**One statement per file, so the file census is a statement census:**

| first statement | files | | first statement | files |
|---|--:|---|---|--:|
| `CREATE TABLE` | 86 | | `CREATE SCHEMA` | 5 |
| `CREATE TRIGGER` | 39 | | `REVOKE …` | 6 |
| `CREATE FUNCTION` / `PROCEDURE` | 28 | | `ALTER SCHEMA` | 5 |
| `CREATE POLICY` | 25 | | `GRANT …` (bootstrap floor) | 4 |
| `CREATE VIEW` | 20 | | `COMMENT ON` | 3 |
| `CREATE ROLE` | 17 | | `INSERT INTO` (seed) | 2 |
| `ALTER TABLE` | 15 | | `CREATE INDEX` (incl. unique/inverted) | 8 |
| `CREATE TYPE` | 7 | | `ALTER DEFAULT PRIVILEGES` | 1 |

### 0.1 · Two numbers that are not the same number

This tree has been counted two ways, and the difference is not a rounding error.

| | census | **deployment** |
|---|---|---|
| driver | `scripts/proof/gate_refusal.py`'s own chain | `trappoint migrate up` |
| on a failing file | logs it and **continues** | marks the version `dirty` and **stops** |
| bookkeeping | none | `trappoint.schema_migration`, one row per file |
| what it answers | "how many of these can take effect?" | "does this tree deploy?" |
| before this wave | 246 of 261 | **155 of 261** — halted at `0121_trg_check_materialised`, `[42P01] relation "mainline_ops.outbox" does not exist` |
| now | — | **271 of 271**, exit 0 |

`0121_trg_check_materialised.sql` was file **156 of 261** in apply order, so the halt left
155 applied, `0121` dirty, and 105 files that had never been executed at all by the runner
that executes migrations in production.

Only the right-hand column describes a deployment. It is the number this file quotes, it is
produced by `scripts/chain/apply_chain.py`, and the run is recorded under `evidence/chain/`.
`docs/release/chain-268.md` is the release note.

---

## 1 · The five files that are the authority

| File | What it is authoritative for | Who writes it |
|---|---|---|
| `migrations.allocation.toml` | **numbers** — which band, which owner, rendered or authored | a human, carefully (MR-6) |
| `migrations.lock.json` | the manifest of what is on disk | **generated**; `trappoint migrate lock --write` |
| `invariants/mi_catalogue.yaml` | the thirty `MI` invariants and their status | a human, plus a projected field |
| `invariants/MI-CATALOGUE.md` | the same, rendered | **generated**; `mi_ratchet reconcile --write` |
| `GRANTS.yaml` | roles, grants and the denial set | a human (DM-7) |

Two of those five are generated. Editing a generated file by hand creates a second
source of truth, which is the exact class of failure the migration reconciliation of
2026-08-08 exists to end: the pre-dispatch collision check compared two *declarations*
with each other, reported zero collisions, and was wrong by twenty numbers. Everything
here compares a file against **one** declaration instead.

---

## 2 · The one filename convention (MR-5)

```
NNNN[a-z]_lower_snake_slug.sql
```

* **`NNNN`** — exactly four decimal digits, zero-padded, allocated by
  `migrations.allocation.toml`.
* **`[a-z]`** — an optional **single** lowercase letter. Ordering is lexicographic on the
  whole stem, so `0006a < 0006b < 0007` and `0119a < 0120`. Two legal uses:
  1. **multi-statement slot** — one logical object needing more than one top-level
     statement: `0058_blocking_check.sql`, then `0058a_bc_open_index.sql`;
  2. **band overflow** — a full band absorbs new work by suffixing its own last number
     rather than borrowing a neighbour's. *This is the mechanism that stops the 2026-08-08
     incident recurring: a worker who runs out of numbers suffixes, never borrows.*
  `x` is reserved for comment/marker-only files (`0009x_covenant_comment.sql`).
* **`_lower_snake_slug`** — `[a-z0-9_]+`. **No second dot, ever.** `.fallback.sql`,
  `.variant.sql` and `.v2.sql` fail discovery's version regex, and one such filename makes
  the runner refuse **every migration in the directory** — measured: one file made
  `trappoint migrate` refuse all 121 beside it. Capability variants live in
  `verticals/mainline/db/ext/<topic>/`.
* **`.sql` and nothing else.** There is **no down migration and there never will be**.
  `.up.sql` is therefore banned — not as a style preference, but because it advertises a
  `.down.sql` that DM-14 makes illegal by construction, and because a suffix chain is what
  let two conventions coexist in one directory invisibly.

**Exactly one top-level SQL statement per file.** The runner does not wrap a body in a
transaction, because CockroachDB DDL inside a multi-statement transaction can fail at
`COMMIT` even when every statement succeeded. A two-statement file is therefore not
atomic, and a failure leaves a half-applied file that nobody can diagnose. One statement
makes `dirty` answerable in seconds.

---

## 3 · The mandatory header block

Four keys, in the **leading comment block** — not "somewhere in the first N characters",
because a rule whose window can be widened by adding SQL is a rule that erodes.

```sql
-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- MAINLINE · 0033_event.sql
-- CREATE TABLE mainline.event — the incident, and the only thing that may write blame
--
-- MI: MI11, MI14
-- I: I05
-- COUNSEL-GATED: no
-- RATIONALE: The event is the root of every blame edge, so it exists before anything
--            that can cite one. Severity is projected, never supplied.
--
CREATE TABLE mainline.event (...);
```

| Key | Rule | Why it is checked and not merely conventional |
|---|---|---|
| `MI:` | exactly one line, ≥1 `MInn`, every id **adopted** by `mi_catalogue.yaml` | `owning_migrations` is a *projection* of this line. A citation of an unadopted id would amend a numbered catalogue by comment. |
| `I:` | exactly one line | TRAPPOINT's SemVer'd public invariants, `I01`–`I16`. |
| `COUNSEL-GATED:` | first word `yes` or `no` | DM-17's set has to be addressable by query, not by search. Repeating the key is allowed when the answers **agree** (the counsel-gated files carry the long `yes (G0) · DEFAULT: … · ADR: …` form beside the short one); two different answers are refused. |
| `RATIONALE:` | non-empty prose, continuation lines joined | It is what a reviewer reads instead of re-deriving the decision from the DDL. |

A **rendered** file additionally carries `-- @rendered-by  trappoint render` and
`-- @template  <path>`, and **is never hand-edited**: a change to it is a change to its
template followed by a re-render of *both* bindings (`verticals/mainline/vertical.toml`
and `packages/trappoint-sql/refvertical/vertical.toml`).

---

## 4 · Rendered or authored, decided by object (MR-1)

Every number belongs to exactly one mode, and the mode is declared in the allocation:

> **RENDERED** — emitted by a template in `packages/trappoint-sql/templates/`.
> **AUTHORED** — written directly in this vertical.
>
> The seam is drawn by **object**, and the test is: *would a second TRAPPOINT vertical
> need this object to pass `trappoint-conform`?* If yes it is substrate and it is a
> template. If no it is vertical and it is authored. `permit` is substrate whoever types
> it; `site` is vertical whoever types it.

Three consequences that are not negotiable:

1. **A rendered file is never deleted to resolve a collision** — the next
   `trappoint render` recreates it.
2. **A hand-authored twin of a rendered file is permanently red, in the worst way.**
   `trappoint render --check` is a zero-diff assertion, and a twin under a different name
   is not a diff — so CI stays green while the runner refuses the tree. *CI green, deploy
   dead.* Lint rule B is what catches it, by comparing a **file** against a
   **declaration**.
3. **`0200` and above is UNALLOCATED and no file may use it, in either mode.** A number
   space with no owner is exactly what produced two conventions.

---

## 5 · The band table

Thirty-three bands, exhaustive and disjoint over the key space `(1, "")` to `(9999, "z")`.
`packages/trappoint-migrate/tests/test_allocation.py` asserts exhaustive-and-disjoint; the
`files` column below is **projected from disk** by `trappoint migrate lock --write` and is
not a declaration.

| band | owner | mode | files |
|---|---|---|--:|
| `0001-0018z` | kernel/render-and-foundation | rendered | 42 |
| `0019-0020z` | datamodel/dm-foundation | authored | 3 |
| `0021-0023z` | kernel/render-and-foundation | rendered | 3 |
| `0024-0031z` | datamodel/dm-spine | authored | 9 |
| `0032-0039z` | datamodel/dm-blame | authored | 8 |
| `0040-0046z` | recall/recall-ddl-triggers | authored | 7 |
| `0047-0049` | datamodel/dm-spine | authored | 3 |
| `0049a-0049z` | algorithms | authored | **6** |
| `0050-0053z` | kernel/subject-and-pin | rendered | 5 |
| `0054-0057z` | datamodel/ex-dm-gate | authored | 4 |
| `0058-0064z` | kernel/obligation-and-clearance | rendered | 9 |
| `0065-0065z` | datamodel/ex-dm-gate | authored | 3 |
| `0066-0068z` | kernel/obligation-and-clearance | rendered | 4 |
| `0069-0070z` | datamodel/ex-dm-disposition | authored | 3 |
| `0071-0071z` | kernel/subject-and-pin+quickrefuse | rendered | 5 |
| `0072-0079z` | custody | authored | 9 |
| `0080-0089z` | recall | authored | **13** |
| `0090-0099z` | datamodel/dm-periphery | authored | **3** |
| `0100-0109z` | kernel/projection-triggers | rendered | 10 |
| `0110-0114z` | recall | authored | 5 |
| `0115-0119` | kernel/merge-gate-and-core | rendered | 5 |
| `0119a-0119z` | kernel/quickrefuse | rendered | 2 |
| `0120-0129z` | kernel/projection-triggers | rendered | 19 |
| `0130-0135z` | kernel/merge-gate-and-core+quickrefuse | rendered | 3 |
| `0136-0139z` | recall | authored | 5 |
| `0140-0144z` | datamodel/dm-functions-triggers+algorithms | authored | 6 |
| `0145-0149z` | datamodel/dm-functions-triggers+algorithms | authored | **12** |
| `0150-0154z` | algorithms | authored | 3 |
| `0155-0169z` | datamodel/dm-views-rls | authored | 15 |
| `0170-0179z` | datamodel/dm-views-rls | authored | 3 |
| `0180-0198z` | datamodel/dm-views-rls | authored | 43 |
| `0199-0199z` | datamodel/dm-views-rls | authored | 1 |
| `0200-9999z` | **UNALLOCATED** | unallocated | **0** |
| | | | **271** |

The four bolded bands are the ones the producer-completion wave of 2026-08-10 grew. No
`first`, `last`, `owner` or `mode` moved; only the `contents` prose was restated to name the
new files, and only by the wave that added them (producers-plan D3).

---

## 6 · Every consumer has a producer

The tree spent a week in a state where triggers, views and row-level-security policies had
been written for tables **nobody had written a `CREATE TABLE` for**. It cost 15 files
directly and it stopped `trappoint migrate up` dead at file 156 of 261 — because a `CREATE
TRIGGER` on v26.2.5 *does* resolve its table, and forward-only means nothing below a halt is
ever executed.

Seven tables were missing. All seven now exist, and the numbers were not chosen freely: the
consumers' `requires:` headers, `GRANTS.yaml`'s `since:` keys, `ARCHITECTURE.md` §18 and
`RLS-MATRIX.yaml` had already fixed each one, and moving any of them would have falsified
four committed artefacts.

| producer | relation | the consumers it unblocks |
|---|---|---|
| `0049d_identity_assignment` | `mainline.identity_assignment` | `0140a` (fn body), `0145a_trg_cbm_account_guard` |
| `0089_agent_action` | `mainline_meas.agent_action` | `0164_v_agent_actions`, `0165_v_gate_latency_daily`, `0166_v_txn_restart_daily` |
| `0089a_person_measure_policy` | `mainline_meas.person_measure_policy` | `0089b` (`NOT NULL REFERENCES`), `0171`, `0172` |
| `0089b_standing` | `mainline_meas.standing` | `0171_v_standing_components`, `0172_v_my_record`, `0187_standing_rls_enable`, `0187a`–`0187e` |
| `0090_patrol_run` | `mainline.patrol_run` | `0163_v_fixity_coverage` |
| `0099_outbox` | `mainline_ops.outbox` | `0101` (fn body), `0121_trg_check_materialised`, `0198x_no_rls_on_cdc_sources` |
| `0099a_site_register_signal` | `mainline_ops.site_register_signal` | `RLS-MATRIX.yaml` `rls_forbidden`; `test_mi_rls.py::test_site_register_signal_has_no_row_level_security` |

Three of them additionally carry an append-only weld — `0145f`, `0149a`, `0149b` — because
MI01 is cited by the very views that read them. **`mainline_ops.outbox` deliberately has no
weld**: it is one of the three allow-listed row-level-TTL tables (30 days), and a
`BEFORE DELETE` refusal trigger would make the expiry job fail forever.

**This class of defect is now refused at lint time.** `trappoint migrate lint` carries a
`producer-absent` rule: every schema-qualified relation a migration references must have a
producer in the same tree. Its red output — captured against the tree *before* the seven
tables landed — is in `evidence/producers/`.

Eleven further relations are named by `GRANTS.yaml` and produced by nothing:
`discordance_warrant`, `document_intake_finding`, `drift_finding`, `lesson`,
`merge_conflict`, `observed_assertion`, `propagation`, `resolution_memory`, `time_witness`,
`mainline_meas.assay_outcome`, `mainline_meas.external_attestation`. **None of them blocks a
migration** — no file in this tree references one — so they are *reported, not authored*
(producers-plan D12). `grants apply --allow-missing` skips them by name and the census is
recorded in `evidence/chain/`.

---

## 7 · What is banned, and what the ban buys

**`CREATE SEQUENCE`, `nextval(`, `SERIAL`, `unique_rowid()` — anywhere, including
templates.** Measured on this cluster: `CREATE SEQUENCE` *succeeds*, so the lint is
load-bearing and not decorative.

The claim it protects, in full, because it is the sentence that stops being true the
moment one migration slips through: the event ledger is gap-free **by compare-and-swap** —
`UNIQUE (subject, prev_seq)` — and not by a sequence. A CockroachDB sequence is allowed to
leave gaps; a rolled-back transaction consumes a value, and `unique_rowid()` is not dense
by construction. So under a sequence a gap in the ledger means *nothing*: it might be
tampering or it might be Tuesday. Under CAS, **a gap MEANS tampering**, and that sentence
is the whole evidentiary value of the ledger.

A convention cannot hold that. A lint can.

`FAMILY` is a **reserved keyword** on this platform and is never used as a bare column name.

Also refused, by ruling rather than by this runner: a `CHECK` containing a subquery,
`now()`, a JSONB operator or a UDF-of-column (DM-4); `DEFERRABLE INITIALLY DEFERRED`
(unimplemented on this platform); row-level TTL outside the three allow-listed tables; and
any system-generated constraint, index or policy name (DM-10 — *the constraint name is
the courtroom exhibit, and `check_permit_1` is not an exhibit*).

---

## 8 · The protected floor (DM-14)

The floor is **`0149z`** — the end of the trigger bands. At or below it a `.down.sql` is
refused **before the runner opens a connection**, because a down migration discovered
halfway through has already dropped something.

> Down-migrating an append-only ledger is not a rollback, it is destruction of evidence.

Above the floor, DM-14 permits one: dropping a view destroys nothing. In practice there
are none anywhere, because MR-5 removed the suffix from the world — `discover()` raises on
any `.down.sql`, at any number. The floor constant exists so that the *rule* can be
stated, cited and tested (`packages/trappoint-migrate/tests/test_protected_floor.py`),
not to open a door.

---

## 9 · Applying a migration, and what the runner refuses

```
trappoint migrate bootstrap --dsn "$TRAPPOINT_DSN"
trappoint migrate up --dsn "$TRAPPOINT_DSN" \
    --tree mainline --migrations verticals/mainline/db/migrations
trappoint migrate grants apply --dsn "$TRAPPOINT_DSN"
trappoint migrate status --dsn "$TRAPPOINT_DSN" --tree mainline
```

Or, from a fresh database with the run recorded as evidence — which is what CI and the
release note quote:

```
python scripts/chain/apply_chain.py            # see scripts/chain/README.md
```

`apply` is an alias of `up`. The bookkeeping lives in schema **`trappoint`**, created
idempotently by `bootstrap` and **outside the numbered set** (DM-13) — otherwise migration
`0001` has nowhere to record that it ran.

The runner refuses, and each refusal is a decision rather than a surprise:

| Refusal | Trigger | What to do |
|---|---|---|
| `BootstrapMissing` | bookkeeping absent | `bootstrap`; a migration with no record is the failure this runner exists to prevent |
| `LockUnavailable` | another migrator holds the lease | wait, or find them. There are **no advisory locks** in CockroachDB, so `trappoint.schema_lock` is a real table with a real lease |
| `DirtyMigration` | a previous run left `applying`/`dirty` | `force <version> --incident <id> --resolve applied\|pending`. A dirty schema is a custody event, which is why clearing one requires an incident id and writes an attestation row. **In a build loop the answer is a fresh database, not a force** |
| `MigrationTreeInvalid` | a file's sha changed after it was applied; a new file sorts *before* the last applied one; an applied version has no file | all three mean the same thing — the stream on disk is not the stream that produced this schema. Write a new migration; forward-only means the applied file is history |
| `SchemaJobFailed` | the statement returned but the job did not | a DDL statement starts a background job. The version does not advance on `SHOW JOBS` reaching anything but success |
| `AttestationDrift` | the live schema disagrees with the chain head | something changed the schema outside this runner, or the chain was edited. Both are the same alarm and neither is a warning |

**`40001` is the only retryable code.** Nothing else is retried, ever — not even a failed
DDL statement, because "did it happen" is answered by `SHOW JOBS`, not by trying again.

**Budget the run.** `--attest each` (the default) recomputes the live schema fingerprint —
twice, and compares — after **every** statement, over a schema that is growing. Measured:
≈5–6 s/file, so a full-tree run is 25–30 minutes on an idle local node and longer on a
contended one. Iterate with `--attest final`; take the record run with `--attest each`.

---

## 10 · Two fingerprints

```
trappoint migrate fingerprint                  # the INPUTS. No cluster.
trappoint migrate fingerprint --live --dsn …   # the SCHEMA, incl. trigger source
trappoint migrate attest --dsn … --expect <hex>
```

The **tree** fingerprint hashes the migration and seed files. DM-12 calls it the
dev/demo/prod parity gate, which is why every seed uses a fixed literal
`'2026-08-05T00:00:00Z'` and `uuid5` identities and **never** `now()` or
`gen_random_uuid()`: one `now()` in a seed makes parity unprovable.

The **live** fingerprint hashes `SHOW CREATE ALL SCHEMAS/TYPES/TABLES` plus
`pg_get_triggerdef()` and `pg_get_functiondef()`, and appends it to a chained ledger. It
puts the merge gate's own source text inside the hash, so **nobody can quietly weaken the
trigger that prevents quietly weakening controls**. Where either routine is absent the run
records `attestation_grade = 'weak'` — the claim softens *in the data*, not only in the
prose.

Both are computed **twice** and refuse when the two computations disagree. A fingerprint
that flickers is worse than no fingerprint: it trains everybody to ignore the alarm.

The chain's ordinals are **dense by compare-and-swap** (`UNIQUE (prev_ordinal)`), so a gap
is not a lost row — it is a rewrite. `apply_chain.py` asserts density on every recorded run
and stores the answer as `attestation.chain_dense`.

---

## 11 · Roles and grants are not migrations (DM-7)

`GRANTS.yaml` is a declarative matrix, re-asserted idempotently:

```
trappoint migrate grants plan       # the SQL, to read before it runs
trappoint migrate grants apply --dsn …
trappoint migrate grants apply --dsn … --allow-missing   # mid-build: report absences, do not refuse
trappoint migrate grants denials    # the negative space, as data
```

A migration runs once. **A `RESTORE` into a new cluster does not carry role membership or
grants**, so they must be re-asserted and drift-checked. DR-8 is the accepted cost: a
freshly restored cluster is unusable until `grants apply` runs, which is better than one
that looks correct and is not.

`--allow-missing` reports a grant whose object does not exist instead of refusing. That is
legitimate while the tree is mid-build and a **defect on a finished cluster** — which is why
the census of what it skipped is recorded in `evidence/chain/` rather than discarded.

The real control is the `denials:` block and the privilege probe that asserts `42501` for
every forbidden (role, object) pair. A matrix listing only what is *permitted* would be a
document about intentions.

---

## 12 · Adding a migration — the whole checklist

1. **Find your band** in `migrations.allocation.toml` (§5 above renders it). If your band is
   full, suffix your own last number. **Never borrow a neighbour's**; ask the owner.
2. **Check the mode.** `rendered` means you edit a template and re-render *both* bindings.
   `authored` means you write the file here.
3. **One statement.** Declare secondary indexes inline in `CREATE TABLE` (DM-6), including
   partial and inverted ones — that is how one-statement-per-file survives without an
   index-file explosion.
4. **Write the header block**, citing an `MI` the catalogue has adopted. If the invariant
   you need does not exist, that is an ADR, not a comment.
5. **If you reference a table, make sure this tree produces it** — and if it does not, write
   the producer or do not write the consumer. `trappoint migrate lint`'s `producer-absent`
   rule will refuse you, and §6 is the week that rule was bought with.
6. **Write the failing test first** and let it fail *for the right reason*. `mi-red`
   requires every `pending` invariant to have a currently-failing owning test; a suite for
   a product whose deliverable is a refusal, that has never been red, asserts nothing.
7. **Run the four commands** at the top of this file.
8. **Regenerate the manifest**: `trappoint migrate lock --write`, then `trappoint migrate
   lock` with no flag — it must print *is current*.
9. **Drive the whole tree through the real runner**: `python scripts/chain/apply_chain.py`.
   A green lint is not a green deployment; §0.1 is what that distinction cost.
10. When the mechanism lands and the test goes green, `mi-red` will fail with
    *"MIxx is pending but its tests pass — promote it"*. **That is the ratchet working.**
    Flip `status: enforced` in `mi_catalogue.yaml`, run
    `python scripts/mi_ratchet.py reconcile --write`, and commit. The promotion is in blame
    forever, and demoting it later needs an `ADR-NNNN` in the commit body.
