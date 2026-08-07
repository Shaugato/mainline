<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: Apache-2.0
-->

# `trappoint-migrate`

Forward-only CockroachDB schema migrations, with a real lock table, a dirty marker that
refuses to advance, and a **gap-free-by-compare-and-swap schema attestation chain**.

```bash
just up                                   # local single-node CockroachDB, no cloud account
uv run trappoint migrate bootstrap        # the `trappoint` bookkeeping schema
uv run trappoint migrate up  --tree trappoint-ref --migrations packages/trappoint-sql/refvertical/sql
uv run trappoint migrate status --tree trappoint-ref
uv run trappoint migrate attest           # non-zero if the live schema drifted
uv run trappoint migrate lint             # the sequence ban, and the citation rule
```

---

## Why not golang-migrate

golang-migrate is the right tool for this platform on the merits: it ships a dedicated
`cockroachdb` driver that takes mutual exclusion through a **real lock table** rather
than PostgreSQL advisory locks (which CockroachDB does not have), it wraps its own
bookkeeping in a retry-correct transaction, and it runs the migration body outside an
explicit transaction, which is exactly right for CockroachDB DDL.

It was still dropped, for one reason:

> **The runner must write the schema attestation inside the same connection discipline
> that writes the ledger.**

With an external binary, the sequence is *apply, exit, reconnect, attest*. Between the
exit and the attest there is a window in which the schema has changed and nothing has
recorded what it changed to. For a product whose entire proposition is that the record
can be trusted, that window is not an implementation detail — it is the thing being
sold. So the DDL and the attestation happen on one connection, in one process, under
one lock lease.

Everything else this package does is a consequence of a CockroachDB fact rather than of
taste. They are worth listing because each one is a place a PostgreSQL-shaped migrator
is quietly wrong here.

| Fact | What it forces |
|---|---|
| DDL inside a multi-statement transaction can fail at `COMMIT` even when every statement succeeded | **One statement per file.** A multi-statement file is not atomic, so a failure leaves a half-applied file and an undiagnosable `dirty` marker. |
| A schema change is a **background job**; the statement returns first | `SHOW JOBS` is polled to terminal success before the version advances. |
| There are **no advisory locks** | `trappoint.schema_lock` is a real table with a real lease, taken over only after genuine expiry. |
| `SHOW CREATE ALL TABLES` omits triggers and routines | The fingerprint adds `pg_get_triggerdef()` and `pg_get_functiondef()`. |
| `SHOW CREATE ALL TABLES` does not guarantee intra-category ordering | Statements are normalised and **sorted** before hashing, and the fingerprint is computed **twice** in one run to assert it is stable. |
| Sequences may leave gaps | `CREATE SEQUENCE` / `nextval(` / `SERIAL` / `unique_rowid()` are refused by `lint`. |

---

## The attestation chain is a ledger, and it is built like one

`trappoint.schema_attestation` is not a log table. It is chained, dense, and
compare-and-swap sequenced:

```sql
CONSTRAINT schema_attestation_pkey    PRIMARY KEY (ordinal),
CONSTRAINT attestation_chain_linear   UNIQUE (prev_ordinal),
CONSTRAINT attestation_chain_dense    CHECK  (ordinal = prev_ordinal + 1),
```

Two migrators that both read head `N` and both try to write `N+1` produce **one commit
and one `23505`**. The loser is not retried, because it read a stale head and retrying
would hide the fact that two migration streams were running against one cluster.

The three mechanisms deliberately overlap. Measured against CockroachDB v26.2.5 the
exhibit is `schema_attestation_pkey` — the primary key is what the second writer meets
first — and `attestation_chain_linear` is what still refuses when the dense `CHECK` is
removed. Stated rather than hidden, because the honest claim is *"this refuses at
depth 2"*, not *"this constraint is what refuses"*.

The payoff is one sentence, and it is the reason `CREATE SEQUENCE` is banned rather than
discouraged:

> **A gap in this table means a row was deleted.**

Under a sequence, a gap means nothing — a rolled-back transaction consumes a value, and
`unique_rowid()` is not dense by construction. The claim only survives if *no* migration
anywhere reintroduces a sequence, which a convention cannot guarantee and a lint can.

Each row also carries `prev_fingerprint`, so `trappoint migrate status` can walk the
chain and report the two distinguishable tampering shapes separately: a **gap** (a row
was deleted) and a **fingerprint mismatch** (a row was rewritten).

### The gate attests to itself

`pg_get_triggerdef()` puts the merge gate's own source text inside the hash. Nobody can
quietly weaken the trigger that prevents quietly weakening controls, because weakening
it changes the fingerprint, and the fingerprint is in a chain that cannot be edited
without leaving one of those two shapes behind.

**GT-05, measured.** `pg_get_triggerdef()` and `pg_get_functiondef()` are both present in
`pg_catalog.pg_proc` on **CockroachDB CCL v26.2.5** (`x86_64-w64-mingw32`, built
2026-07-28), verified locally on 2026-08-07 by running this command against a
single-node cluster:

```
$ trappoint migrate attest
grade       strong (covers: schemas, types, tables, triggers, routines)
```

The fallback is kept anyway, and it is not decoration: the runner probes the catalogue
rather than assuming, and if either routine is absent it hashes the table-granular view
and writes `attestation_grade = 'weak'` **into the row**. The claim softens in the data,
not only in the prose — a run whose attestation was weak is never indistinguishable from
one whose attestation was strong. What is *not* yet verified is behaviour on CockroachDB
Cloud Standard, where the SQL identity differs; the probe answers that question wherever
it runs, which is the point of probing.

---

## `dirty` is a custody event

A failed statement marks its version `dirty`, records the SQLSTATE and the database's
own message, and stops. Forward progress is refused until a human resolves it:

```bash
uv run trappoint migrate force 0071a_merge_record --incident INC-2026-0042 --resolve applied
```

`--incident` is required, and `--resolve` has **no default** — `applied` and `pending`
produce different schemas, and a runner that guessed would be guessing about production.
The resolution writes an attestation row of kind `force` carrying the incident id, and
`CONSTRAINT force_cites_an_incident` makes an unattributed force physically impossible
to store.

---

## `lint`

```
trappoint migrate lint --root verticals/mainline/db/migrations --root packages/trappoint-sql/templates
```

Two rules:

1. **The sequence ban** (`CREATE SEQUENCE`, `nextval(`, `SERIAL`, `BIGSERIAL`,
   `unique_rowid()`), over every migration file and every template.
2. **The citation rule** — every migration file cites at least one `MI\d\d` or `I\d\d`
   in its **header comment**, per ARCHITECTURE.md §18. In the header, where a reviewer
   reads it; not three hundred lines down inside a constraint name.

The lint runs over code with SQL comments removed, using a small lexer that understands
`'…'`, `"…"`, `$$…$$` and `$tag$…$tag$`. That is not fussiness: a naive `grep` fires on
the comment that *explains* the ban (so the guard gets weakened, which is how guards
die) and misses a token inside a dollar-quoted PL/pgSQL body (which is exactly where a
trigger function would reintroduce one).

It also refuses a migration file containing more than one statement, counted over the
lexed text so that semicolons inside a routine body are not mistaken for terminators.

An empty tree passes with zero findings, and the file count is always printed, so a run
that checked nothing is never mistaken for a run that checked everything.

---

## What this package does **not** do

* **No down migrations.** A `.down.sql` file is refused, not ignored. Append-only means
  append-only, and a down migration that only works above the ledger floor is a trap.
* **No declarative diffing.** A differ that mis-plans a trigger, an RLS policy or a
  C-SPANN vector index emits a `DROP` an append-only ledger cannot survive.
* **No retry of anything except `40001`,** and only for bookkeeping transactions. DDL is
  attempted exactly once, ever. The loop is hand-written in `db.py`; `tenacity`,
  `backoff` and `retrying` are forbidden repository-wide by `.importlinter` contract 4.
* **No changefeed creation.** Changefeeds are cluster jobs, not schema. Putting
  `CREATE CHANGEFEED` in a migration makes migrations non-idempotent across
  environments and couples DDL to S3 credentials.

## Licence

Apache-2.0. Part of the TRAPPOINT substrate.
