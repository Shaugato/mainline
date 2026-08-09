<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: Apache-2.0
-->

# `trappoint-migrate`

Forward-only CockroachDB schema migrations, with a real lock table, a dirty marker that
refuses to advance, and a **gap-free-by-compare-and-swap schema attestation chain**.

Every `uv run` below is scoped with `--package`. A bare `uv run` builds every workspace
member, so an unrelated distribution mid-edit three directories away would break a
command that has nothing to do with it. `just` wraps all of this: `just bootstrap`,
`just migrate`, `just status`, `just attest`, `just lint-sql`.

```bash
just up                                   # local single-node CockroachDB, no cloud account
uv run --package trappoint-migrate trappoint migrate bootstrap        # the `trappoint` bookkeeping schema
uv run --package trappoint-migrate trappoint migrate up  --tree trappoint-ref --migrations packages/trappoint-sql/refvertical/sql
uv run --package trappoint-migrate trappoint migrate status --tree trappoint-ref
uv run --package trappoint-migrate trappoint migrate attest           # non-zero if the live schema drifted
uv run --package trappoint-migrate trappoint migrate lint             # sequences, citations, the header block
```

The whole surface, and which half of it needs a database:

| Command | Cluster? | What it is for |
|---|---|---|
| `lint` | no | the sequence ban, the filename convention, the allocation, the header block |
| `lock [--write]` | no | `migrations.lock.json` — a **generated** manifest, never authored (MR-6) |
| `fingerprint` | no | the **inputs** digest: DM-12's dev/demo/prod parity gate |
| `verify --offline` | no | every hermetic check above, in one exit code |
| `image` | no | the one CockroachDB version constant, read out of `compose.yaml` |
| `bootstrap` | yes | the `trappoint` bookkeeping schema, idempotently (DM-13) |
| `up` / `apply` | yes | forward-only apply, one statement at a time, attested per file |
| `status` | yes | applied · pending · dirty · the attestation chain, walked |
| `attest` | yes | recompute the live fingerprint and compare it with the chain head |
| `fingerprint --live` | yes | the **schema** digest, including trigger and routine source |
| `grants plan\|apply\|denials` | apply only | `GRANTS.yaml` re-asserted; DM-7 |
| `force --incident <id>` | yes | resolve a dirty version, on the record |
| `verify` | yes | the offline checks **plus** bookkeeping cleanliness and drift |

`apply` is an alias of `up`. `docs/leads/datamodel.md` §1.3 publishes the verb as
`apply`; the kernel shipped `up`, and every workflow in the repository and every
cluster's bookkeeping already names it — so both spellings exist and neither is a second
implementation.

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
uv run --package trappoint-migrate trappoint migrate force 0071a_merge_record --incident INC-2026-0042 --resolve applied
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

1. **The sequence ban** (`CREATE SEQUENCE`, `nextval(`, `SERIAL`, `BIGSERIAL`,
   `unique_rowid()`), over every migration file and every template.
2. **The citation rule** — every migration file cites at least one `MI\d\d` or `I\d\d`
   in its **header comment**, per ARCHITECTURE.md §18. In the header, where a reviewer
   reads it; not three hundred lines down inside a constraint name.
3. **The filename convention** (rule A), the **allocation** (rule B) and the **`.up.sql`
   ban** (rule C) — MR-5 and MR-6. Rule B is the one that matters most, because it
   compares a *file* against a *declaration* rather than comparing two declarations with
   each other, which is the thing the 2026-08-08 collision check could not do.
4. **The mandatory header block** — `MI:`, `I:`, `COUNSEL-GATED:`, `RATIONALE:`, read
   from the **leading comment block** and resolved against that tree's
   `invariants/mi_catalogue.yaml`. An `MI` id the catalogue has not *adopted* is refused:
   §16 is amended by an ADR, not by a header comment, and the catalogue's `proposed:`
   block is deliberately not a registry. Pass `--no-headers` to skip it, and
   `--strict-invariants` to additionally refuse an `-- I:` citation outside `I01`–`I16`
   — off by default, because two files in this repository cite `I17` and turning another
   lane red is that lane owner's decision, not a side effect of landing a linter.

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

---

## The seam to custody: `attest.LedgerSink`

A schema change is a custody event, and the custody domain wants every one of them —
every applied migration, every drift alarm, every `force` under an incident — hashed into
the MAINLINE ledger. But this package must not import the custody package: it is
Apache-2.0 substrate that a second vertical forks, the ledger is FSL-1.1 vertical code,
and `.importlinter`'s layering contract refuses that direction.

So the direction is inverted. `LedgerSink` is a `typing.Protocol` with one method:

```python
from trappoint_migrate.attest import LedgerSink, set_default_sink


class CustodySink:
    def emit(
        self, kind: str, subject_id: str, payload: dict[str, object]
    ) -> None: ...  # write a ledger entry


set_default_sink(CustodySink())  # installed once, process-wide. No edit to this package.
```

Three clauses, each load-bearing:

* `emit` is called **after** the attestation row commits, never before — the chain is the
  record of last resort, and a sink that ran first could publish a schema change that then
  failed to commit;
* `emit` **must not raise**, and if it does the migration still succeeds: a sink whose bug
  turned an applied migration into a *reported* failure would leave a schema that did
  change and a caller who believes it did not, which is strictly the worst outcome
  available. The exception lands in `attest.SINK_FAILURES`, which `status` prints, so the
  swallow is bounded and "custody was not told" is itself on the record;
* `payload` is JSON-shaped — bytes are hex-encoded by the caller, because a ledger entry
  has to survive a round trip.

The default is `NullLedgerSink`, which *remembers* rather than discards, so a test can
assert what the runner emitted before a real sink is swapped in.

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
