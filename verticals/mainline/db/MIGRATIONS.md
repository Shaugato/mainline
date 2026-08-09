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
uv run trappoint migrate lint          # naming, allocation, sequences, header block
uv run trappoint migrate lock          # the manifest is derived and current
uv run trappoint migrate verify --offline
python scripts/mi_ratchet.py check     # the invariant catalogue is committed and current
```

---

## 0 · The five files that are the authority

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

## 1 · The one filename convention (MR-5)

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

## 2 · The mandatory header block

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

## 3 · Rendered or authored, decided by object (MR-1)

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

## 4 · What is banned, and what the ban buys

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

Also refused, by ruling rather than by this runner: a `CHECK` containing a subquery,
`now()`, a JSONB operator or a UDF-of-column (DM-4); `DEFERRABLE INITIALLY DEFERRED`
(unimplemented on this platform); row-level TTL outside the three allow-listed tables; and
any system-generated constraint, index or policy name (DM-10 — *the constraint name is
the courtroom exhibit, and `check_permit_1` is not an exhibit*).

---

## 5 · The protected floor (DM-14)

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

## 6 · Applying a migration, and what the runner refuses

```
uv run trappoint migrate bootstrap --dsn "$TRAPPOINT_DSN"
uv run trappoint migrate up --dsn "$TRAPPOINT_DSN" \
    --tree mainline --migrations verticals/mainline/db/migrations
uv run trappoint migrate grants apply --dsn "$TRAPPOINT_DSN"
uv run trappoint migrate status --dsn "$TRAPPOINT_DSN" --tree mainline
```

`apply` is an alias of `up`. The bookkeeping lives in schema **`trappoint`**, created
idempotently by `bootstrap` and **outside the numbered set** (DM-13) — otherwise migration
`0001` has nowhere to record that it ran.

The runner refuses, and each refusal is a decision rather than a surprise:

| Refusal | Trigger | What to do |
|---|---|---|
| `BootstrapMissing` | bookkeeping absent | `bootstrap`; a migration with no record is the failure this runner exists to prevent |
| `LockUnavailable` | another migrator holds the lease | wait, or find them. There are **no advisory locks** in CockroachDB, so `trappoint.schema_lock` is a real table with a real lease |
| `DirtyMigration` | a previous run left `applying`/`dirty` | `force <version> --incident <id> --resolve applied\|pending`. A dirty schema is a custody event, which is why clearing one requires an incident id and writes an attestation row |
| `MigrationTreeInvalid` | a file's sha changed after it was applied; a new file sorts *before* the last applied one; an applied version has no file | all three mean the same thing — the stream on disk is not the stream that produced this schema. Write a new migration; forward-only means the applied file is history |
| `SchemaJobFailed` | the statement returned but the job did not | a DDL statement starts a background job. The version does not advance on `SHOW JOBS` reaching anything but success |
| `AttestationDrift` | the live schema disagrees with the chain head | something changed the schema outside this runner, or the chain was edited. Both are the same alarm and neither is a warning |

**`40001` is the only retryable code.** Nothing else is retried, ever — not even a failed
DDL statement, because "did it happen" is answered by `SHOW JOBS`, not by trying again.

---

## 7 · Two fingerprints

```
uv run trappoint migrate fingerprint                  # the INPUTS. No cluster.
uv run trappoint migrate fingerprint --live --dsn …   # the SCHEMA, incl. trigger source
uv run trappoint migrate attest --dsn … --expect <hex>
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

---

## 8 · Roles and grants are not migrations (DM-7)

`GRANTS.yaml` is a declarative matrix, re-asserted idempotently:

```
uv run trappoint migrate grants plan       # the SQL, to read before it runs
uv run trappoint migrate grants apply --dsn …
uv run trappoint migrate grants denials    # the negative space, as data
```

A migration runs once. **A `RESTORE` into a new cluster does not carry role membership or
grants**, so they must be re-asserted and drift-checked. DR-8 is the accepted cost: a
freshly restored cluster is unusable until `grants apply` runs, which is better than one
that looks correct and is not.

The real control is the `denials:` block and the privilege probe that asserts `42501` for
every forbidden (role, object) pair. A matrix listing only what is *permitted* would be a
document about intentions.

---

## 9 · Adding a migration — the whole checklist

1. **Find your band** in `migrations.allocation.toml`. If your band is full, suffix your
   own last number. **Never borrow a neighbour's**; ask the owner.
2. **Check the mode.** `rendered` means you edit a template and re-render *both* bindings.
   `authored` means you write the file here.
3. **One statement.** Declare secondary indexes inline in `CREATE TABLE` (DM-6), including
   partial and inverted ones — that is how one-statement-per-file survives without an
   index-file explosion.
4. **Write the header block**, citing an `MI` the catalogue has adopted. If the invariant
   you need does not exist, that is an ADR, not a comment.
5. **Write the failing test first** and let it fail *for the right reason*. `mi-red`
   requires every `pending` invariant to have a currently-failing owning test; a suite for
   a product whose deliverable is a refusal, that has never been red, asserts nothing.
6. **Run the four commands** at the top of this file.
7. **Regenerate the manifest**: `trappoint migrate lock --write`.
8. When the mechanism lands and the test goes green, `mi-red` will fail with
   *"MIxx is pending but its tests pass — promote it"*. **That is the ratchet working.**
   Flip `status: enforced` in `mi_catalogue.yaml`, run
   `python scripts/mi_ratchet.py reconcile --write`, and commit. The promotion is in blame
   forever, and demoting it later needs an `ADR-NNNN` in the commit body.
