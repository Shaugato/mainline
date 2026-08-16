<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# CENSUS · W5 — CockroachDB schema, type and index features

**Worker:** W5 · **Plan:** [`docs/submission/feature-census-plan.md`](../feature-census-plan.md) ·
**Date measured:** 2026-08-16 · **HEAD:** `5f57146` · **Deadline:** 2026-08-18 17:00 EDT

This file owns the **declarative half of the database**: types, generated columns, indexes,
constraints and referential shape. It carries the plan's **R8** correction and flags it for W7.

---

## 0. HOW TO CHECK ANY NUMBER ON THIS PAGE IN UNDER A MINUTE

Two probes. The first is one paste; the second is one `curl`.

### 0.1 The whole census, in one statement

```bash
docker exec -i trappoint-crdb ./cockroach sql --insecure -d mainline_demo --format=table < census.sql
```

`census.sql` is reproduced in **§8**. Run 2026-08-16, output verbatim:

```
         measured         |  n
--------------------------+------
  CHECK constraints       | 461
  FKs with 3 columns      | 2
  FKs with >1 column      | 19
  FOREIGN KEY constraints | 107
  PRIMARY KEY constraints | 89
  TSVECTOR columns        | 1
  UNIQUE constraints      | 27
  VECTOR columns          | 4
  base tables             | 89
  enum labels             | 36
  enum types              | 7
  generated STORED cols   | 8
  indexes STORING         | 9
  indexes cspann          | 3
  indexes expression      | 0
  indexes hash-sharded    | 0
  indexes inverted/GIN    | 5
  indexes partial         | 6
  indexes total           | 178
  indexes unique          | 116
  sequences               | 0
  views                   | 20
(22 rows)
```

Two of those numbers reconcile against each other, which is the cheapest possible integrity check
on the rest: `PRIMARY KEY constraints 89` + `UNIQUE constraints 27` = `indexes unique 116`, and
`indexes total 178` − `116` = 62 non-unique secondary indexes. Six application schemas —
`trappoint`, `mainline`, `mainline_meas`, `mainline_ops`, `mainline_audit`, `mainline_qa`.

### 0.2 The bridge from that local cluster to the public origin

The strongest single artefact in this file. `mainline.blocking_check.dedupe_key` is a **generated
`STORED` column whose value is a SHA-256 the database computes**. The live origin serves it, and
the local cluster's own generated value is byte-identical:

```bash
curl -s https://ihuuyvm4z6nfuktihnkey77fpy0eyrhj.lambda-url.ap-southeast-1.on.aws/v1/permits/dec0de00-0006-4000-8000-000000000001/blocking-checks
#   … "dedupe_key":"c4bd7e3a46a5c52c60384a8bef53e40a716dd46d2a5bad38f7f36528d312329c" …

docker exec trappoint-crdb ./cockroach sql --insecure -d mainline_demo \
  -e "SELECT encode(dedupe_key,'hex') FROM mainline.blocking_check WHERE check_id='dec0de00-0007-4000-8000-000000000001';"
#   c4bd7e3a46a5c52c60384a8bef53e40a716dd46d2a5bad38f7f36528d312329c
```

Both measured 2026-08-16. Neither the API nor the seed ever writes that column; CockroachDB
computes it from six other columns. It is the same value on two independent clusters because it
is a function of the row, not of the writer.

### 0.3 The one word this file is disciplined about

A row is marked **LIVE** only where the feature was observed **on the public origin today**, by a
request reproduced in the row. Everything else that is real and applied is marked **REPO**, in the
exact construction `docs/submission/feature-census-plan.md` R4 gives Bedrock. There is no third
reading. Where a feature is applied on the live cluster but no anonymous request reaches it, the
row says so in one sentence rather than blurring the state.

---

## 1. RULING R8 — THE VECTOR-COLUMN CORRECTION · **W7 MUST PROPAGATE THIS**

> **The old claim:** "5 live VECTOR columns."
> **Measured:** 4 columns of SQL type `VECTOR`, plus 1 column of type `TSVECTOR`. The old count
> reached five by counting the `tsvector` as a vector column.

**The corrected claim is stronger than the wrong one, and this is the sentence W7 should carry:**

> **4 `VECTOR` columns across 4 tables, indexed by 3 `cspann` distributed vector indexes, each of
> which is required to declare prefix columns — *and*, in the same schema, a generated `TSVECTOR`
> column with 5 inverted indexes beside it. That is hybrid lexical-plus-dense memory in one
> database, with no second engine and no sync job.**

The probe, run 2026-08-16:

```sql
SELECT table_schema, table_name, column_name, crdb_sql_type
FROM information_schema.columns WHERE crdb_sql_type ILIKE 'VECTOR%' ORDER BY 1,2,3;
```
```
  table_schema |     table_name      | column_name | crdb_sql_type
---------------+---------------------+-------------+----------------
  mainline     | clause_embedding    | embedding   | VECTOR(1024)
  mainline     | event_cue_coarse    | emb_coarse  | VECTOR(256)
  mainline     | event_cue_embedding | emb         | VECTOR(1024)
  mainline     | event_cue_stage     | emb         | VECTOR(1024)
(4 rows)
```
```sql
SELECT table_schema, table_name, column_name, data_type FROM information_schema.columns
WHERE data_type='tsvector' AND table_schema='mainline';
```
```
  table_schema | table_name | column_name | data_type
---------------+------------+-------------+-----------
  mainline     | event_cue  | tsv         | tsvector
(1 row)
```

Note the fourth vector column, `event_cue_stage.emb`: it is a **staging** table and carries **no**
`cspann` index. 4 vector columns and 3 vector indexes is not an inconsistency — it is the reason
the two numbers must be quoted separately.

**Actions for W7.**

1. Replace every occurrence of "5 live VECTOR columns" with the corrected sentence above.
2. The number **3** (`cspann` indexes) belongs to **W3**, who owns the index rows and the
   prefix-column rule. This file owns the **columns**, the **`tsvector`** and the **hybrid framing**.
3. `evidence/tool-usage/crdb-features.json` has no row for full-text search, generated columns,
   enums, partial indexes or composite FKs. Per **R6** every row below carries its detector so the
   generator can be extended without a hand-written census drifting away from it.

**The one-command proof of the hybrid claim** — a single `EXPLAIN`, both arms in one plan, run
2026-08-16 (abridged; full statement in §8):

```
  • union all
  ├── • scan
  │         table: event_cue@cue_tsv                       ← lexical, GIN over the generated tsvector
  └── • top-k
      └── • lookup join
          └── • vector search
                table: event_cue_embedding@cue_scoped_idx  ← dense, cspann
                target count: 5
                prefix spans: [/'0000…0001'/'0000…0001'/'body' - /'0000…0001'/'0000…0001'/'body']
```

The optimizer chose both without a hint. `prefix spans` on the last line is the prefix-column rule
W3 documents, visible in a plan.

---

## 2. TYPES

### 7 user-defined enum types, 36 labels

```
state:         LIVE
what it is:    Seven CREATE TYPE … AS ENUM domains that make the project's vocabularies — hazard
               band, control delta, state machine alphabet, evidential basis — types the server
               enforces, rather than strings the application hopes are spelled right.
where:         verticals/mainline/db/migrations/0010_type_control_delta.sql:26
               …/0011_type_subject_state.sql:27      …/0012_type_disposition_kind.sql:27
               …/0013_type_virulence_class.sql:26    …/0014_type_blame_basis.sql:26
               …/0015_type_blame_state.sql:26        …/0016_type_prop_state.sql:26
verify in 60s: four GETs against the live origin, in §2.1 — every one of the seven types has a
               label in a public response body
say this:      "Seven of this schema's vocabularies are CockroachDB enum types, not strings. All
               thirty-six labels are declared in migrations 0010 to 0016, and every one of the
               seven types has a label you can read in a response from the public demo URL."
never say:     "the enums are validated in the API" — they are validated by the type; the API
               never sees an invalid label. Also never say the enum set is extensible at runtime:
               adding a label is a migration.
detector (R6): SELECT typname, count(*) FROM pg_type t JOIN pg_enum e ON e.enumtypid=t.oid GROUP BY 1
```

Measured 2026-08-16:

```
   schema  |    enum_type     | labels |                       label_list
-----------+------------------+--------+---------------------------------------------------------
  mainline | blame_basis      |      4 | asserted_document, asserted_human, derived_documentary,
           |                  |        | inferred_semantic
  mainline | blame_state      |      4 | active, provisional, dormant, refuted
  mainline | control_delta    |      5 | introduce, strengthen, restate, weaken, remove
  mainline | disposition_kind |      6 | applied, mitigated, mechanism_absent, escalated,
           |                  |        | accept_residual, emergency_override
  mainline | prop_state       |      6 | proposed, already_present, conflicted, adopted,
           |                  |        | declined, revoked
  mainline | subject_state    |      7 | draft, checks_materialised, dispositioned, merged,
           |                  |        | suspended, closed, abandoned
  mainline | virulence_class  |      4 | routine, serious, blood_major, blood_fatal
(7 rows)
```

#### 2.1 All seven types, live, in four requests

Base URL abbreviated to `$U`; measured 2026-08-16.

| type | request | the label in the body |
|---|---|---|
| `subject_state` | `GET $U/v1/demo/subjects` | `"state":"dispositioned"`, `"state":"checks_materialised"` |
| `blame_basis` | `GET $U/v1/clauses/dec0de00-0004-4000-8000-000000000001/ancestry` | `"basis":"asserted_document"` |
| `blame_state` | same request | `"state":"active"` |
| `virulence_class` | same request | `"virulence":"blood_major"` |
| `control_delta` | same request | `"control_delta":"introduce"` |
| `prop_state` | `GET $U/v1/lessons/dec0de00-0005-4000-8000-000000000001/propagation` | `"state":"adopted"`, `"already_present"`, `"conflicted"` |
| `disposition_kind` | `GET $U/v1/checks/dec0de00-0007-4000-8000-000000000001/disposition` | `"kind":"applied"`, `"emergency_override"`, `"escalated"`, `"mitigated"`, `"mechanism_absent"` |

Three requests carry five of the seven; the fourth carries the remaining two.

#### 2.2 The type does two jobs the application would otherwise do badly

Both measured 2026-08-16.

**It refuses an unknown label, at the type boundary:**

```sql
SELECT 'catastrophic'::mainline.virulence_class;
--  ERROR: invalid input value for enum virulence_class: "catastrophic"
--  SQLSTATE: 22P02
```

**And declaration order *is* severity order** — `enum_range` returns the declared sequence and the
comparison operators respect it, so "is this worse than that" is a type-level fact, not a lookup
table somebody has to keep sorted:

```sql
SELECT v FROM unnest(enum_range(NULL::mainline.virulence_class)) AS v;
--  routine / serious / blood_major / blood_fatal   (in that order)
SELECT 'blood_fatal'::mainline.virulence_class > 'routine'::mainline.virulence_class;
--  t
```

`say this:` — *"'Worse than' is not application logic here. `blood_fatal > routine` is true in SQL
because the enum's declaration order is its sort order."*

---

## 3. GENERATED `STORED` COLUMNS — 8, AND THREE OF THEM ARE THE STORY

One probe returns all eight with their expressions:

```sql
SELECT table_schema, table_name, column_name, data_type, generation_expression
FROM information_schema.columns WHERE is_generated='ALWAYS'
ORDER BY table_schema, table_name, column_name;
```

Measured 2026-08-16 (expressions verbatim, wrapped for width):

```
  table_schema |      table_name      |   column_name    | data_type | generation_expression
---------------+----------------------+------------------+-----------+-----------------------------------
  mainline     | blocking_check       | dedupe_key       | bytea     | digest(COALESCE(permit_id::STRING,'-')||'|'||COALESCE(cr_id::STRING,'-')||'|'||clause_uuid::STRING||'|'||encode(commit_id,'hex')||'|'||COALESCE(precursor_event_id::STRING,'-')||'|'||origin, 'sha256')
  mainline     | boundary_certificate | unmodelled_total | integer   | tags_unmodelled + under_declared
  mainline     | cbm_account          | balanced         | boolean   | inherited = ((((carried + split_carried) + merge_carried) + residue_open) + residue_disposed)
  mainline     | cr_event             | chain_digest     | bytea     | digest(prev_digest || payload::STRING::BYTES, 'sha256')
  mainline     | event_cue            | tsv              | tsvector  | to_tsvector('english', cue_text)
  mainline     | identity_assignment  | descendant_key   | uuid      | COALESCE(descendant_clause_uuid, '00000000-0000-0000-0000-000000000000')
  mainline     | mechanism_predicate  | term_count       | integer   | COALESCE(jsonb_array_length(CASE WHEN jsonb_typeof(ast->'terms')='array' THEN ast->'terms' ELSE NULL END), 0)
  mainline     | permit_event         | chain_digest     | bytea     | digest(prev_digest || payload::STRING::BYTES, 'sha256')
(8 rows)
```

**One correction to the incoming brief, downward and deliberate.** The brief describes
`blocking_check.dedupe_key` as "a sha256 over eight coalesced fields". Measured, it is a SHA-256
over **six** columns — `permit_id`, `cr_id`, `clause_uuid`, `commit_id`, `precursor_event_id`,
`origin` — of which **three** are `COALESCE`-guarded because they are nullable. Six-with-three-
guarded is the checkable claim; eight is not.

### 3.1 `permit_event.chain_digest` and `cr_event.chain_digest` — a hash chain the database computes

```
state:         LIVE
what it is:    A SHA-256 hash chain over an append-only event log, computed by CockroachDB as a
               column definition — the writer cannot supply the digest, because the column is
               GENERATED ALWAYS AS … STORED.
where:         verticals/mainline/db/migrations/0059_permit_event.sql:55  (permit_event)
               verticals/mainline/db/migrations/0060_cr_event.sql:55      (cr_event)
               live write path: verticals/mainline/apps/demo-api/src/mainline_demo_api/
                                transitions.py:781-790  — the INSERT names nine columns and
                                chain_digest is not one of them
verify in 60s: the SQL in §3.2 — it recomputes the digest and links row 2 to row 1, and prints
               "t" twice. First expected line: "seq | stored_generated_column | …"
say this:      "The permit's event log is a SHA-256 hash chain, and CockroachDB computes it. The
               column is GENERATED ALWAYS AS (digest(prev_digest || payload, 'sha256')) STORED —
               the application inserts the payload and the previous link, and is structurally
               incapable of choosing the digest."
never say:     (1) "the live URL serves chain_digest" — it does not; no declared route returns
                   the column. What the origin serves is head_seq, the chain's length.
               (2) "the generated column makes the log tamper-proof." It makes the digest
                   unforgeable *given the inputs*. Verifying that prev_digest is the real
                   predecessor is a TRIGGER's job (mainline.fn_permit_event_chain) — W6's row.
                   The repository already states this: tests/integration/custody/nemesis/
                   attacks.py:1498 is titled "the chain_digest was computed server-side; its
                   INPUT was not."
detector (R6): information_schema.columns WHERE is_generated='ALWAYS' AND column_name='chain_digest'
```

The migration's own comment is the close block's line, and it is checkable at
`0059_permit_event.sql:35`:

> `chain_digest   COMPUTED BY THE SERVER`

**What the live origin does show:** `GET $U/v1/permits/dec0de00-0006-4000-8000-000000000001`
returns `"head_seq":2` — the live permit's chain has two links. `mainline_api` holds
`INSERT, SELECT` on `mainline.permit_event` (probe in §7), so the append path is a granted live
path, and `transitions.py:781-790` is its only INSERT.

### 3.2 The chain, verified — paste this

Scoped to the demo permit, so the output is the same for every reader:

```sql
SELECT seq,
       encode(chain_digest,'hex')                                            AS stored_generated_column,
       encode(digest(prev_digest || payload::STRING::BYTES,'sha256'),'hex')  AS recomputed_now,
       chain_digest = digest(prev_digest || payload::STRING::BYTES,'sha256') AS matches
FROM mainline.permit_event
WHERE permit_id = 'dec0de00-0006-4000-8000-000000000001' ORDER BY seq;
```
```
  seq |                     stored_generated_column                      | … | matches
------+------------------------------------------------------------------+---+---------
    1 | 26d77d20df4ad9afb2a063116082ded8b28364567428a27154919549176c6f60 | … |    t
    2 | b1f89979c86288ea9b53d41b1c722d967970b012be3eef9f8d2c94fb291ae1bf | … |    t
```

And the *link*, which is what makes it a chain rather than a pile of digests. Written as a
whole-table invariant, so it stays true as the demo runs and the log grows:

```sql
SELECT bool_and(e2.prev_digest = e1.chain_digest) AS every_link_holds, count(*) AS links_checked
FROM mainline.permit_event e2
JOIN mainline.permit_event e1 ON e1.permit_id=e2.permit_id AND e1.seq=e2.prev_seq;
--   every_link_holds | links_checked
--          t         |             2
```

Row 2's `prev_digest` is `26d77d20…`, which is row 1's database-computed `chain_digest`.

**Read the digests, not the row count.** `mainline.permit_event` is an append-only log on a shared
development cluster, so `count(*)` moves whenever anyone exercises a transition — it was 2 rows at
the start of this census and 4 an hour later, from a parallel run. The two digests above did not
move, and `every_link_holds` is the assertion worth quoting: it is a property of the chain, not of
its length.

**One more invariant on the same table, and it is easy to miss.**
`0059_permit_event.sql` declares `UNIQUE INDEX linear (permit_id, prev_seq)`. A given predecessor
can be claimed **once**. Two concurrent appends that both read `seq 2` as their parent do not
produce a fork — one commits and the other gets `23505` on `linear`. The chain is single-threaded
by a unique index, not by a lock the application remembers to take.

### 3.3 `event_cue.tsv` — full-text search as a column definition

```
state:         REPO
what it is:    A generated TSVECTOR column, to_tsvector('english', cue_text), kept in step with
               the text by the database and indexed by a GIN index — full-text retrieval with no
               second engine and no sync job.
where:         verticals/mainline/db/migrations/0040_event_cue.sql:51
               index: cue_tsv, CREATE INDEX … USING gin (tsv)
verify in 60s: EXPLAIN SELECT cue_id FROM mainline.event_cue
                 WHERE tsv @@ to_tsquery('english','isolation & valve');
               expected: a "• inverted filter" node over "table: event_cue@cue_tsv"
say this:      "The lexical half of retrieval is a generated column. `to_tsvector('english',
               cue_text)` is the column's definition, so the search index cannot fall behind the
               text — and it sits in the same schema, the same transaction and the same backup as
               the dense vectors."
never say:     "the demo searches text at the live URL." It does not: mainline.event_cue carries
               NO grant to mainline_api at all (§7), so no anonymous request reaches it. The
               column and its index are applied on the cluster; the retrieval path is exercised in
               the repository, not through the demo URL.
detector (R6): information_schema.columns WHERE data_type='tsvector' AND is_generated='ALWAYS'
```

Measured 2026-08-16:

```
EXPLAIN SELECT cue_id FROM mainline.event_cue WHERE tsv @@ to_tsquery('english','isolation & valve');

  • inverted filter
  │ estimated row count: 1
  │ inverted column: tsv_inverted_key
  │ num spans: 2
  │
  └── • scan
        table: event_cue@cue_tsv
        spans: 2 spans
```

### 3.4 `blocking_check.dedupe_key` — the database computes the identity of a memory

```
state:         LIVE
what it is:    A SHA-256 over six columns of the row, generated STORED, carrying a UNIQUE index —
               so the identity of a materialised obligation is computed by the server and the
               writer cannot choose it.
where:         verticals/mainline/db/migrations/0058_blocking_check.sql:89-95 (column)
               verticals/mainline/db/migrations/0058_blocking_check.sql:110    (UNIQUE (dedupe_key))
               index name on the cluster: blocking_check_dedupe_key_key
verify in 60s: the curl / docker pair in §0.2 — the live origin and the local generated column
               print the same 64 hex characters
say this:      "An agent that writes the same obligation twice — because it crashed, retried, or
               simply did not remember — creates one row. Not because the agent is careful:
               because the identity of the row is a SHA-256 the database computes from the row's
               own contents, and it is UNIQUE."
never say:     "the live demo shows the duplicate being refused." It does not. mainline_api holds
               SELECT and UPDATE on mainline.blocking_check and NOT INSERT (§7), which is the
               standing materialise_checks gap the founder has not closed. The live origin serves
               the computed dedupe_key; the refusal is demonstrated on a cluster, in §3.5.
detector (R6): pg_indexes WHERE indexdef ILIKE '%dedupe_key%' AND indexdef ILIKE 'CREATE UNIQUE%'
```

The migration comment says it in the repository's own words, at `0058_blocking_check.sql:87-88`:

> `GT-13 PASS (v26.2.5): digest() is legal inside a STORED generated column, so`
> `the SERVER computes the obligation's identity and the inserter cannot choose it.`

### 3.5 That refusal, demonstrated

Run 2026-08-16 in scratch database `w_w5` on the same v26.2.5 node — a faithful miniature of
`0058`, with a random-UUID primary key so that the *only* thing stopping the second write is the
generated column:

```sql
CREATE TABLE dedupe_demo (
  check_id UUID NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  permit_id UUID NULL, cr_id UUID NULL, clause_uuid UUID NOT NULL, origin STRING NOT NULL,
  dedupe_key BYTES AS (digest(COALESCE(permit_id::STRING,'-')||'|'||COALESCE(cr_id::STRING,'-')
              ||'|'||clause_uuid::STRING||'|'||origin,'sha256')) STORED,
  UNIQUE INDEX dedupe_demo_dedupe_key_key (dedupe_key)
);
INSERT INTO dedupe_demo (permit_id,cr_id,clause_uuid,origin) VALUES
  ('dec0de00-0006-4000-8000-000000000001', NULL,
   'dec0de00-0004-4000-8000-000000000001', 'blame_ancestry');   -- INSERT 0 1

-- byte-for-byte the same four values again; check_id defaults to a NEW random UUID
INSERT INTO dedupe_demo (permit_id,cr_id,clause_uuid,origin) VALUES
  ('dec0de00-0006-4000-8000-000000000001', NULL,
   'dec0de00-0004-4000-8000-000000000001', 'blame_ancestry');
```
```
ERROR: duplicate key value violates unique constraint "dedupe_demo_dedupe_key_key"
SQLSTATE: 23505
DETAIL: Key (dedupe_key)=('\x0d3ed09ff1e45a9c3490f687131d9708d4d67c51eccb8409234045bea541da2f') already exists.
CONSTRAINT: dedupe_demo_dedupe_key_key
```

The miniature hashes **four** columns where `mainline.blocking_check` hashes six — it drops
`commit_id` and `precursor_event_id` so the paste has no `encode(…,'hex')` in it. That is why the
digest above is not the `c4bd7e3a…` of §0.2: different input, same mechanism. If you want the
production digest, read it from the live URL and the cluster as §0.2 does.

The primary keys differed — `gen_random_uuid()` gave each row its own. The write was refused
anyway, because the *content* was the same and the database had already hashed it.

### 3.6 `identity_assignment.descendant_key` — a generated column inside a PRIMARY KEY

```
state:         REPO
what it is:    A nullable UUID cannot sit in a primary key, so the schema generates a NOT NULL
               surrogate — COALESCE(descendant_clause_uuid, all-zero UUID) — and puts that in the
               key instead, closing the "NULL is never equal to NULL" uniqueness hole.
where:         verticals/mainline/db/migrations/0049d_identity_assignment.sql:217-220 (the column)
               verticals/mainline/db/migrations/0049d_identity_assignment.sql:222     (the key)
               verticals/mainline/db/migrations/0049d_identity_assignment.sql:110     (the reason,
                 headed "WHY A NULLABLE COLUMN IS COALESCED INTO A STORED ONE, AND KEYED ON")
verify in 60s: docker exec trappoint-crdb ./cockroach sql --insecure -d mainline_demo \
                 -e "SHOW CREATE TABLE mainline.identity_assignment;"
               expected: the descendant_key line above, then the PRIMARY KEY naming it
say this:      "'This ancestor clause has no descendant' is a fact that has to be unique, and NULL
               is not unique to NULL. So the key is a generated column: COALESCE of the nullable
               UUID with a zero UUID, NOT NULL, in the primary key."
never say:     "descendant_clause_uuid is NOT NULL." It is nullable — that is the entire point.
               `absent_has_no_descendant CHECK (relation != 'absent' OR descendant_clause_uuid IS
               NULL)` is on the same table and depends on it staying nullable.
detector (R6): pg_indexes WHERE indexdef ILIKE '%descendant_key%'
```

The other three generated columns — `boundary_certificate.unmodelled_total`,
`cbm_account.balanced`, `mechanism_predicate.term_count` — are arithmetic and JSONB derivations
kept honest by the server. `cbm_account.balanced` is worth one sentence: it is a **boolean
generated column that states whether a conservation equation holds**, so "the books balance" is a
column you can `WHERE` on rather than a report somebody runs.

---

## 4. INDEXES

### 4.1 6 partial indexes, used as invariants

```
state:         REPO  (see the per-index note; signing_credential_by_signer is on a live-granted table)
what it is:    Indexes with a WHERE clause. Two of the six are UNIQUE, which makes them
               constraints that apply to a SUBSET of rows — a rule SQL has no other way to state.
where:         one_live_disposition          verticals/mainline/db/migrations/0066a_one_live_disposition.sql:37
               carriage_one_open             verticals/mainline/db/migrations/0048_carriage.sql:99
               carriage_open                 verticals/mainline/db/migrations/0048_carriage.sql:100
               signing_credential_by_signer  verticals/mainline/db/migrations/0023_signing_credential_index.sql:22
               ir_open                       verticals/mainline/db/migrations/0049_identity_residue.sql:139
               by_site_open                  verticals/mainline/db/migrations/0077_unwitnessed_debt.sql:96
verify in 60s: SELECT indexname, indexdef FROM pg_indexes WHERE indexdef ILIKE '%WHERE%';
               expected first row: "carriage | carriage_one_open | CREATE UNIQUE INDEX …"
say this:      "Six of this schema's indexes carry a WHERE clause, and two of them are UNIQUE. A
               partial unique index is a uniqueness rule that applies to a subset of rows: a
               permit may accumulate any number of retracted clearances, and at most one live one.
               There is no application code in that sentence."
never say:     "we validate that there is only one live disposition." Nothing validates it. The
               index makes a second one unrepresentable.
detector (R6): pg_indexes WHERE indexdef ILIKE '%WHERE%' — split on 'CREATE UNIQUE'
```

Measured 2026-08-16, all six, verbatim:

```
  tablename          |          indexname           | indexdef
---------------------+------------------------------+-----------------------------------------------------------
  carriage           | carriage_one_open            | CREATE UNIQUE INDEX carriage_one_open ON … carriage
                     |                              |   USING btree (series_id ASC, doc_id ASC)
                     |                              |   WHERE (closed_commit IS NULL)
  carriage           | carriage_open                | CREATE INDEX carriage_open ON … carriage
                     |                              |   USING btree (doc_id ASC) WHERE (closed_commit IS NULL)
  disposition        | one_live_disposition         | CREATE UNIQUE INDEX one_live_disposition ON … disposition
                     |                              |   USING btree (check_id ASC) WHERE (retracted_by IS NULL)
  identity_residue   | ir_open                      | CREATE INDEX ir_open ON … identity_residue
                     |                              |   USING btree (site_id ASC, commit_id ASC)
                     |                              |   WHERE (disposition_id IS NULL)
  signing_credential | signing_credential_by_signer | CREATE INDEX signing_credential_by_signer ON …
                     |                              |   USING btree (signer_sub ASC) WHERE (revoked_at IS NULL)
  unwitnessed_debt   | by_site_open                 | CREATE INDEX by_site_open ON … unwitnessed_debt
                     |                              |   USING btree (site_code ASC, incurred_at ASC)
                     |                              |   WHERE (discharged_tree_size IS NULL)
(6 rows)
```

**The migration says why, and it is the best sentence available to the film.**
`0066a_one_live_disposition.sql:34-35`:

> `A trigger would be a second mechanism to disable; an index is a physical impossibility.`

#### The invariant, demonstrated

Run 2026-08-16 in `w_w5`, same v26.2.5 node, same index shape as `one_live_disposition`:

```sql
CREATE TABLE live_demo (check_id INT NOT NULL, note STRING NOT NULL, retracted_by STRING NULL,
                        PRIMARY KEY (check_id, note));
CREATE UNIQUE INDEX one_live ON live_demo (check_id) WHERE retracted_by IS NULL;

INSERT INTO live_demo VALUES (1,'first',NULL);                -- INSERT 0 1
INSERT INTO live_demo VALUES (1,'second-live-attempt',NULL);
--  ERROR: duplicate key value violates unique constraint "one_live"
--  SQLSTATE: 23505
--  DETAIL: Key (check_id)=(1) already exists.
--  CONSTRAINT: one_live

INSERT INTO live_demo VALUES (1,'a-retracted-one','someone');        -- INSERT 0 1
INSERT INTO live_demo VALUES (1,'another-retracted-one','someone-else'); -- INSERT 0 1
```

Two rows for `check_id = 1` were accepted and a third was refused. What separates them is the
predicate. **`retracted_by IS NULL` is the entire specification, and it is enforced by storage.**

#### The optimizer names it, and CockroachDB prints the words

```
EXPLAIN SELECT disposition_id FROM mainline.disposition
 WHERE check_id='00000000-0000-0000-0000-000000000001' AND retracted_by IS NULL;

  • scan
    table: disposition@one_live_disposition (partial index)
    spans: [/'00000000-0000-0000-0000-000000000001' - /'00000000-0000-0000-0000-000000000001']
```

CockroachDB's `EXPLAIN` writes `(partial index)` itself. That is the shortest proof of the feature
anyone can produce.

**The same is true of the credential lookup, and that query is in the deployed package.**
`verticals/mainline/apps/demo-api/src/mainline_demo_api/credentials.py:109-114` is
`WHERE signer_sub = %s AND revoked_at IS NULL` — the index's predicate, exactly — and its
docstring at line 98 says the index "exists for this exact lookup":

```
EXPLAIN SELECT credential_id FROM mainline.signing_credential
 WHERE signer_sub='demo' AND revoked_at IS NULL ORDER BY credential_id;

  • scan
    table: signing_credential@signing_credential_by_signer (partial index)
    spans: [/'demo' - /'demo']
```

`never say:` a judge can see that plan from the URL — `EXPLAIN` is a cluster-side command. The
live claim is narrower and still good: the query in the deployed Lambda is the index's predicate,
`mainline_api` holds `SELECT` on the table, and the plan choice is reproducible in one command.

#### One migration recorded a risk; the cluster has now settled it

`0048_carriage.sql:81-85` says, in the tree, that inline `UNIQUE INDEX … WHERE` was **unverified**
when the band was written and gives the remediation if v26.2 refused it. Measured today:
`carriage_one_open` is present in `pg_indexes` on the applied cluster in exactly the inline form.
The risk note can stay — it is the record of an honest engineering decision — and the census
records that the platform accepted it.

### 4.2 5 inverted (GIN) indexes — and one of them is a trigram index

```
state:         REPO
what it is:    Five inverted indexes over JSONB-adjacent and array-valued and text columns: array
               containment, the generated tsvector, and a trigram index for substring matching.
where:         cbc_anc              USING gin (site_id ASC, ancestor_events)      — UUID[] containment
               cv_anchors           USING gin (anchor_set)
               cv_trgm              USING gin (canon_text gin_trgm_ops)           — trigram
               cue_tsv              USING gin (tsv)                                — full text
               predicate_watch_set  USING gin (site_id ASC, state ASC, registers)
verify in 60s: SELECT tablename, indexname FROM pg_indexes WHERE indexdef ILIKE '%USING gin%';
               expected: 5 rows, first "clause_blame_closure | cbc_anc"
say this:      "Five inverted indexes sit beside the vector indexes: array containment for blame
               ancestry, a trigram index for substring search over clause text, and a GIN index
               over the generated tsvector. Lexical and dense retrieval are the same database."
never say:     "the trigram index is chosen for our text queries." On the demo corpus it is not —
               see the measured note below.
detector (R6): pg_indexes WHERE indexdef ILIKE '%USING gin%'
```

**Measured, and the honest version is more interesting than the tidy one.** `cbc_anc` is chosen
without a hint for array containment:

```
EXPLAIN SELECT clause_uuid FROM mainline.clause_blame_closure
 WHERE site_id='…'::UUID AND ancestor_events @> ARRAY['…'::UUID];
  • scan
    table: clause_blame_closure@cbc_anc
```

`cv_trgm` is **not** chosen unhinted for `LIKE '%isolation valve%'` on the demo corpus — the plan
full-scans, which is the optimizer costing an empty table correctly. Hinted, the index works and
the plan shows the trigrams:

```
EXPLAIN SELECT clause_uuid FROM mainline.clause_version@cv_trgm WHERE canon_text LIKE '%isolation valve%';
  • inverted filter
  │ inverted column: canon_text_inverted_key
  │ num spans: 10
  └── • scan
        table: clause_version@cv_trgm
```

This is the same posture `verticals/mainline/db/queries/EXPLAIN-ASSERTIONS.md` already takes about
plan assertions under `missing stats`: pin the index, and record what the unhinted plan actually
did rather than what we wish it did.

### 4.3 9 `STORING` (covering) indexes — a CockroachDB-specific clause

```
state:         REPO
what it is:    CockroachDB's STORING clause attaches non-key columns to a secondary index so the
               read is answered from the index alone, with no lookup back into the primary index.
where:         9 indexes; e.g. mainline.refusal_ledger.refusal_ledger_by_subject
                 USING btree (subject_kind, subject_id, observed_at DESC)
                 STORING (constraint_name, sqlstate, diagnosis, naa_kind)
verify in 60s: SELECT tablename, indexname FROM pg_indexes WHERE indexdef ILIKE '%STORING%';
               expected: 9 rows, first "blame_edge | by_event"
say this:      "Nine secondary indexes use CockroachDB's STORING clause to carry the columns the
               read needs, so the answer comes out of one index. The refusal ledger's own index
               stores the constraint name, the SQLSTATE and the diagnosis — the three things you
               ask for when you ask why the database said no."
never say:     "we measured the round-trip saving." No such measurement exists in this tree.
detector (R6): pg_indexes WHERE indexdef ILIKE '%STORING%'
```

### 4.4 Index composition, whole-schema

| kind | n | note |
|---|---|---|
| total indexes | 178 | |
| unique | 116 | = 89 PRIMARY KEY + 27 UNIQUE constraints; the sums reconcile |
| non-unique secondary | 62 | |
| partial (`WHERE`) | 6 | §4.1 — two of them UNIQUE |
| inverted / GIN | 5 | §4.2 |
| `cspann` vector | 3 | **W3's rows** |
| `STORING` | 9 | §4.3 |
| with a `DESC` key column | 16 | newest-first reads keyed in storage order |
| expression indexes | **0** | §6 |
| hash-sharded | **0** | §6 |

The `DESC` row is counted with `indexdef LIKE '% DESC%'`, and it is **16** under either reading —
restricting the match to the key list (`split_part(indexdef,' STORING ',1)`) returns 16 as well, so
no `DESC` appears only inside a `STORING` clause. An earlier draft of this page said 18; the
measured number is 16 and the detector is given so it cannot drift again.

---

## 5. CONSTRAINTS AND REFERENTIAL SHAPE

### 5.1 461 CHECK constraints — and the live origin reads them out of the catalog

```
state:         LIVE
what it is:    461 named CHECK constraints across 89 tables. The demo API does not hold a list of
               them: it queries pg_catalog.pg_constraint at request time and returns the
               catalog's own predicate text.
where:         constraint source: throughout verticals/mainline/db/migrations/
               the live reflection: verticals/mainline/apps/demo-api/src/mainline_demo_api/
                                    reads.py:308-318 (_CONSTRAINTS_SQL) and 332-376 (_gate_constraints)
verify in 60s: curl -s $U/v1/permits/dec0de00-0006-4000-8000-000000000001
               expected: a "constraints" array whose first entry is
               {"constraint":"identity_conserved_when_issued", "predicate":"CHECK (((state !=
                'merged'::mainline.subject_state) OR (open_residue = 0)))", …}
say this:      "Ask the live URL about a permit and it answers with the predicates of the CHECK
               constraints that would refuse to issue it, read out of pg_constraint at request
               time — constraint name, predicate text, and the current value of each counter the
               predicate mentions. Nothing in the API knows those constraints in advance."
never say:     "the API documents the constraints." It reflects them. A constraint added by a
               future migration appears in the response with no code change — reads.py:340-347
               says exactly that, and is the reason the claim is worth making.
detector (R6): pg_constraint WHERE contype='c' AND nspname NOT IN (system schemas)
```

Measured 2026-08-16, from the public URL:

```json
"constraints": [
 {"constraint":"identity_conserved_when_issued",
  "predicate":"CHECK (((state != 'merged'::mainline.subject_state) OR (open_residue = 0)))",
  "counters":[{"column":"open_residue","value":0}], "blamed_by_refusal":false},
 {"constraint":"boundary_certified_when_issued",
  "predicate":"CHECK (((state != 'merged'::mainline.subject_state) OR (unmodelled_asset_count = 0)))",
  "counters":[{"column":"unmodelled_asset_count","value":0}], "blamed_by_refusal":false},
 {"constraint":"gate_closed_when_issued",
  "predicate":"CHECK (((state != 'merged'::mainline.subject_state) OR (open_blocking = 0)))",
  "counters":[{"column":"open_blocking","value":1}], "blamed_by_refusal":false},
 …7 entries in total on mainline.permit, in pg_constraint.oid order…
]
```

Those are the **first three of the seven, in the order the origin returns them** — `ORDER BY
con.oid` at `reads.py:317`. Note what the predicate text also proves, free:
`::mainline.subject_state` is the enum cast, so one request substantiates both §2 and §5.1.

**They are authored CHECKs, not `NOT NULL` in disguise.** The count is from `pg_constraint`
`contype='c'`; of the 461, exactly **4** have a bare `IS NOT NULL` shape and **0** carry an
auto-generated `_not_null` name.

#### The reconciliation, and the trap in it — read this before quoting 7 and 4

The API's filter is one line, `reads.py:361`: `if "'merged'" not in predicate: continue`. It
matches the **quoted enum literal**, not the substring `merged`. Reproduce it in SQL with the
literal quoted, and the naive version beside it:

```sql
SELECT cl.relname AS table_name,
       count(*)                                                                 AS total_checks,
       count(*) FILTER (WHERE pg_get_constraintdef(c.oid) LIKE '%''merged''%')  AS api_selects,
       count(*) FILTER (WHERE pg_get_constraintdef(c.oid) ILIKE '%merged%')     AS naive_grep
FROM pg_constraint c JOIN pg_class cl ON cl.oid=c.conrelid
WHERE c.contype='c' AND cl.relname IN ('permit','change_request') GROUP BY 1 ORDER BY 1;
```
```
    table_name   | total_checks | api_selects | naive_grep
-----------------+--------------+-------------+-------------
  change_request |           11 |           4 |          5
  permit         |           16 |           7 |          8
```

**7 and 4 are the right numbers, and both are confirmed against the live origin today** — the
permit response carries 7 entries, and
`GET $U/v1/change-requests/dec0de00-000c-4000-8000-000000000001` carries exactly 4
(`cr_gate_closed_when_merged`, `cr_merge_evidence`, `cr_conflicts_resolved_when_merged`,
`cr_identity_conserved_when_merged`).

But a reader who checks with an unquoted `ILIKE '%merged%'` gets **8 and 5** and will think the
census cannot count. The extra row in each case is a constraint that mentions the *column*
`merged_commit` and never gates on state — `permit_commit_sized` and `cr_commit_sized`, both
`CHECK ((merged_commit IS NULL) OR (length(merged_commit) = 32))`. Quote the detector with the
quotes in it, or the number will not reproduce.

> **Two drift notes for the orchestrator, neither a claim in this census.**
> 1. `reads.py:343-344`'s docstring says the filter "selects exactly seven of the thirteen CHECKs" on
>    `mainline.permit`. Measured today the table has **16**, and the filter still selects 7 — the
>    behaviour is right and the comment's second number is stale.
> 2. The same docstring describes the seven as "the six gate constraints plus `merge_evidence`".
>    That still holds.
>
> Not W5's file to edit; flagged so it can be corrected before a judge counts.

### 5.2 107 foreign keys, 19 of them composite, 2 of them three-column

```
state:         REPO  (the FK); LIVE (the referenced rows — see below)
what it is:    Multi-column foreign keys that make a legal-transition table and a legal-clearance
               table the authority on what is allowed. An illegal transition is not a rejected
               input; it is a row that does not exist in the referenced table.
where:         legal_edge      verticals/mainline/db/migrations/0059_permit_event.sql:65
               cr_legal_edge   verticals/mainline/db/migrations/0060_cr_event.sql:65
                 both: FOREIGN KEY (subject_kind, from_state, to_state)
                       REFERENCES mainline.subject_transition(subject_kind, from_state, to_state)
                       ON DELETE RESTRICT ON UPDATE RESTRICT
               fk_clearance    verticals/mainline/db/migrations/0066_disposition.sql:165
                 FOREIGN KEY (virulence, kind) REFERENCES mainline.clearance_legal(virulence, kind)
verify in 60s: SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint
                WHERE contype='f' AND array_length(conkey,1)=3;
               expected: 2 rows — cr_legal_edge and legal_edge, definitions as above
say this:      "The permit state machine is a three-column foreign key. Eighteen transitions are
               legal across two subject kinds, out of ninety-eight the alphabet permits, and the
               other eighty are not forbidden by a rule — they are absent from a table. An event
               claiming one is refused with 23503 by referential integrity."
never say:     "the state machine is validated in code." The application never checks the edge.
detector (R6): pg_constraint WHERE contype='f' AND array_length(conkey,1)>1
```

The two referenced tables, measured 2026-08-16:

```sql
SELECT count(*) AS legal_edges, count(DISTINCT subject_kind) FROM mainline.subject_transition;
--  18 legal edges | 2 subject kinds        (the alphabet permits 2 x 7 x 7 = 98)
SELECT count(*) AS legal_pairs FROM mainline.clearance_legal;
--  21 legal pairs                          (4 virulence x 6 disposition_kind = 24 possible)
```

**Three of the twenty-four clearance pairs are missing, and that is the product.** Read straight
off the cluster:

```
   virulence  |                            legal_kinds
--------------+--------------------------------------------------------------------
  routine     | applied, mitigated, mechanism_absent, escalated, accept_residual, emergency_override
  serious     | applied, mitigated, mechanism_absent, escalated, accept_residual, emergency_override
  blood_major | applied, mitigated, mechanism_absent, escalated,                   emergency_override
  blood_fatal | applied, mitigated,                   escalated,                   emergency_override
```

`say this:` — *"You cannot accept residual risk on a hazard that has already killed someone. Not
because a rule engine says no — because `(blood_fatal, accept_residual)` is not a row in the table
the foreign key points at."*

Both facts are checkable read-only, in one statement:

```sql
SELECT EXISTS(SELECT 1 FROM mainline.clearance_legal
              WHERE virulence='blood_fatal' AND kind='accept_residual');  -- f
SELECT EXISTS(SELECT 1 FROM mainline.clearance_legal
              WHERE virulence='routine'     AND kind='accept_residual');  -- t
SELECT EXISTS(SELECT 1 FROM mainline.subject_transition
              WHERE subject_kind='permit' AND from_state='draft' AND to_state='merged');       -- f
SELECT EXISTS(SELECT 1 FROM mainline.subject_transition
              WHERE subject_kind='permit' AND from_state='dispositioned' AND to_state='merged'); -- t
```

**The referenced rows are on the live origin.** `GET $U/v1/checks/dec0de00-0007-4000-8000-000000000001/disposition`
returns a `lattice` array — those are `mainline.clearance_legal` rows for `blood_major`, served
publicly, each carrying `virulence`, `kind`, `min_signer_rank`, `max_ttl_hours` and the five
`req_*` flags. A judge can read the referenced table over HTTP and then check that the pair the
demo refuses is absent from it.

**The refusal, demonstrated** — run 2026-08-16 in `w_w5` with the same two enums and the same
composite FK shape:

```sql
INSERT INTO d3 VALUES (1,'routine','accept_residual');      -- INSERT 0 1
INSERT INTO d3 VALUES (2,'blood_fatal','accept_residual');
--  ERROR: insert on table "d3" violates foreign key constraint "fk_clearance"
--  SQLSTATE: 23503
--  DETAIL: Key (virulence, kind)=('blood_fatal', 'accept_residual') is not present in table "legal3".
--  CONSTRAINT: fk_clearance
```

The full list of 19 composite FKs is one probe away
(`pg_constraint WHERE contype='f' AND array_length(conkey,1)>1`); beyond the two three-column
edges, the recurring two-column shape is `(clause_uuid, commit_id) REFERENCES clause_version` —
**a clause reference always carries the version it refers to**, which is why a stale citation is
not representable. `mainline.disposition` also carries a **self-referencing** FK,
`disposition_retracted_by_fkey (retracted_by) REFERENCES disposition(disposition_id)`: retraction
is an edge inside the table, and it is the same column `one_live_disposition` keys its predicate
off.

### 5.3 3 tables split into COLUMN FAMILIES — including one that isolates a 1024-dim vector

```
state:         REPO
what it is:    CockroachDB's COLUMN FAMILY clause splits a row across storage groups so a read of
               the hot columns does not drag the cold ones off disk. clause_embedding puts its
               VECTOR(1024) in a family of its own.
where:         verticals/mainline/db/migrations/0024_commit_obj.sql:117-118    (f_hot / f_cold)
               verticals/mainline/db/migrations/0029_clause_version.sql:243-247 (f_hot / f_cold)
               verticals/mainline/db/migrations/0031_clause_embedding.sql:151   (f_meta / f_vec)
verify in 60s: docker exec trappoint-crdb ./cockroach sql --insecure -d mainline_demo \
                 -e "SHOW CREATE TABLE mainline.clause_embedding;"
               expected: FAMILY f_meta (clause_uuid, commit_id, site_id, activity_root,
                         embed_model, index_gen) then FAMILY f_vec (embedding)
say this:      "The 1024-dimension embedding lives in its own CockroachDB column family, so
               scanning embedding metadata — which model, which index generation — does not pull
               four kilobytes of floats per row off disk."
never say:     "column families make our vector search faster." Nothing in this tree measures
               that. The claim is that the storage layout is declared, and it is.
detector (R6): grep 'FAMILY ' over SHOW CREATE ALL TABLES
```

`0030_clause_band.sql:35` is worth citing because it records the *negative* decision in the same
band: "why there are no column families: a five-column row with no cold half has nothing to
split." Three tables use the feature; the schema also wrote down where it chose not to.

### 5.4 All 89 base tables carry `WITH (schema_locked = true)`

```
state:         REPO
what it is:    A CockroachDB table setting that declares the table's schema closed to online
               change, which lets the storage layer skip the machinery that supports concurrent
               schema changes.
where:         emitted on every CREATE TABLE; visible in SHOW CREATE
verify in 60s: docker exec trappoint-crdb ./cockroach sql --insecure -d mainline_demo \
                 --format=csv -e "SHOW CREATE ALL TABLES;" | grep -c "schema_locked = true"
               expected: 89 — the same number as base tables
say this:      "Every one of the 89 base tables is declared WITH (schema_locked = true). A schema
               this project treats as a specification is one the cluster is told not to expect
               changes to."
never say:     "schema_locked prevents migrations." It does not; the migration chain unlocks and
               relocks. It declares intent between migrations.
detector (R6): count of 'schema_locked = true' in SHOW CREATE ALL TABLES == count of base tables
```

---

## 6. AUDIT RULINGS — WHAT WAS LOOKED FOR AND IS NOT THERE

Per the brief, these four were specifically audited. Each is a **negative** result, measured, and
each is worth publishing: a checked-and-absent row is a credibility asset (plan R2). **These are
audit rulings, not new census states** — nothing here enters the LIVE / REPO / APPLIED / DECLARED /
NOT-AVAILABLE vocabulary.

| looked for | measured | ruling |
|---|---|---|
| **expression indexes** | **0** | Not used. `pg_indexes` carries no `btree (<function>(…))` form. Do not claim them. |
| **hash-sharded indexes** | **0** | Not used. No `USING HASH`, and no `crdb_internal_%_shard_%` column exists. Do not claim them. |
| **sequences** | **0** | Not used, and **deliberately** — see below. |
| **table partitioning / `PARTITION BY`** | **0 tables** | The only `PARTITION BY` in the tree is a window function inside a view (`OVER (PARTITION BY …)`). Never cite it as table partitioning. |
| **materialized views** | **0** | 20 views, none materialized (3 `mainline`, 14 `mainline_audit`, 3 `mainline_qa`). |
| **FK from `disposition` to `defeater_option`** | **0** | Already required by `docs/submission/MUST-NOT-CLAIM.md`; re-measured today and confirmed. |
| **CHECK constraints** | **461** | Present, in volume — promoted to a full row at §5.1. |

**Sequences: the absence is the design.** Zero sequences, and **34** columns default to
`gen_random_uuid()`. A monotonically increasing sequence is a single hot range in a distributed
database; a random UUID key spreads writes across the keyspace. The schema never reaches for
`SERIAL` or `unique_rowid()`.

On the time side, **48** columns default to bare `now()` and **one** to `now() + '30 days'` — so
`ILIKE '%now()%'` returns **49** and `column_default = 'now()'` returns **48**. Quote whichever you
mean; both are measured today by
`SELECT column_default, count(*) FROM information_schema.columns WHERE column_default ILIKE
'%now()%' GROUP BY 1`.

- `say this:` *"There is not one sequence in this schema. Keys are random UUIDs or content
  digests, because a monotonic counter is a single hot range in a distributed database."*
- `verify in 60s:` `SELECT count(*) FROM information_schema.sequences;` → `0`

**The `defeater_option` gap, re-measured 2026-08-16.** `mainline.disposition` carries **10**
foreign keys and **none** of them points at `mainline.defeater_option`; the only related
constraint is `disposition_defeater_code_stated CHECK (defeater_code != '')`. The database will
accept a defeater code that was never offered; that gap is closed in the application. This census
restates it rather than letting the strength of §5.2 imply that *every* referential rule here is
in the database.

```sql
SELECT count(*) FROM pg_constraint c JOIN pg_class cl ON cl.oid=c.conrelid
JOIN pg_class rf ON rf.oid=c.confrelid
WHERE cl.relname='disposition' AND rf.relname='defeater_option' AND c.contype='f';
--  0
```

---

## 7. REACHABILITY — WHICH OF THESE AN ANONYMOUS JUDGE CAN TOUCH

The demo's SQL role is `mainline_api`. Its grants decide what a request from the public URL can
reach, and they are the reason several rows above are **REPO** rather than **LIVE**. Measured
2026-08-16, read-only:

```sql
SELECT table_name, grantee, string_agg(privilege_type,',' ORDER BY privilege_type) AS privs
FROM information_schema.table_privileges
WHERE table_schema='mainline' AND grantee='mainline_api' AND table_name IN
  ('permit_event','cr_event','blocking_check','disposition','exposure_receipt','signing_credential',
   'clause_version','clause_blame_closure','event_cue','event_cue_embedding','clause_embedding',
   'carriage','identity_assignment')
GROUP BY 1,2 ORDER BY 1;
```
```
      table_name      |   grantee    |     privs
----------------------+--------------+----------------
  blocking_check      | mainline_api | SELECT,UPDATE       ← no INSERT: the standing gap
  clause_blame_closure| mainline_api | SELECT
  clause_version      | mainline_api | SELECT
  cr_event            | mainline_api | SELECT
  disposition         | mainline_api | INSERT,SELECT
  exposure_receipt    | mainline_api | SELECT
  permit_event        | mainline_api | INSERT,SELECT
  signing_credential  | mainline_api | SELECT
(8 rows)
```

`carriage`, `clause_embedding`, `event_cue`, `event_cue_embedding` and `identity_assignment` return
**no row at all** — `mainline_api` holds no privilege on them. Any claim that the demo URL
exercises the tsvector column, the vector columns or the carriage invariants would be false, and
§3.3, §4.1 and R8's framing are worded accordingly.

The `blocking_check` `SELECT,UPDATE`-without-`INSERT` line is the standing `materialise_checks` /
`exposure_receipt` gap. **This census does not propose closing it.** Widening the write surface of
an unauthenticated endpoint is the founder's decision and he has not made it (plan R7).

---

## 8. THE PROBES, IN FULL

### 8.1 `census.sql` — the §0.1 table

```sql
SELECT 'enum types' AS measured, count(DISTINCT t.oid)::STRING AS n
  FROM pg_type t JOIN pg_enum e ON e.enumtypid=t.oid
UNION ALL SELECT 'enum labels',           count(*)::STRING FROM pg_enum
UNION ALL SELECT 'generated STORED cols', count(*)::STRING FROM information_schema.columns
          WHERE is_generated='ALWAYS'
UNION ALL SELECT 'VECTOR columns',        count(*)::STRING FROM information_schema.columns
          WHERE crdb_sql_type LIKE 'VECTOR%'
UNION ALL SELECT 'TSVECTOR columns',      count(*)::STRING FROM information_schema.columns
          WHERE data_type='tsvector' AND table_schema='mainline'
UNION ALL SELECT 'base tables',           count(*)::STRING FROM information_schema.tables
          WHERE table_type='BASE TABLE' AND table_schema NOT IN
          ('pg_catalog','information_schema','crdb_internal','pg_extension')
UNION ALL SELECT 'views',                 count(*)::STRING FROM information_schema.tables
          WHERE table_type='VIEW' AND table_schema NOT IN
          ('pg_catalog','information_schema','crdb_internal','pg_extension')
UNION ALL SELECT 'indexes total',         count(*)::STRING FROM pg_indexes WHERE schemaname NOT IN
          ('pg_catalog','information_schema','crdb_internal','pg_extension')
UNION ALL SELECT 'indexes unique',        count(*)::STRING FROM pg_indexes WHERE schemaname NOT IN
          ('pg_catalog','information_schema','crdb_internal','pg_extension')
          AND indexdef ILIKE 'CREATE UNIQUE%'
UNION ALL SELECT 'indexes partial',       count(*)::STRING FROM pg_indexes WHERE schemaname NOT IN
          ('pg_catalog','information_schema','crdb_internal','pg_extension') AND indexdef ILIKE '%WHERE%'
UNION ALL SELECT 'indexes inverted/GIN',  count(*)::STRING FROM pg_indexes WHERE indexdef ILIKE '%USING gin%'
UNION ALL SELECT 'indexes cspann',        count(*)::STRING FROM pg_indexes WHERE indexdef ILIKE '%USING cspann%'
UNION ALL SELECT 'indexes STORING',       count(*)::STRING FROM pg_indexes WHERE schemaname NOT IN
          ('pg_catalog','information_schema','crdb_internal','pg_extension') AND indexdef ILIKE '%STORING%'
UNION ALL SELECT 'indexes expression',    count(*)::STRING FROM pg_indexes WHERE schemaname NOT IN
          ('pg_catalog','information_schema','crdb_internal','pg_extension')
          AND indexdef ~ 'btree \([a-z_]+\('
UNION ALL SELECT 'indexes hash-sharded',  count(*)::STRING FROM pg_indexes WHERE indexdef ILIKE '%USING HASH%'
UNION ALL SELECT 'sequences',             count(*)::STRING FROM information_schema.sequences
UNION ALL SELECT 'CHECK constraints',     count(*)::STRING FROM pg_constraint c
          JOIN pg_class cl ON cl.oid=c.conrelid JOIN pg_namespace n ON n.oid=cl.relnamespace
          WHERE c.contype='c' AND n.nspname NOT IN ('pg_catalog','information_schema','crdb_internal')
UNION ALL SELECT 'PRIMARY KEY constraints', count(*)::STRING FROM pg_constraint c
          JOIN pg_class cl ON cl.oid=c.conrelid JOIN pg_namespace n ON n.oid=cl.relnamespace
          WHERE c.contype='p' AND n.nspname NOT IN ('pg_catalog','information_schema','crdb_internal')
UNION ALL SELECT 'UNIQUE constraints',    count(*)::STRING FROM pg_constraint c
          JOIN pg_class cl ON cl.oid=c.conrelid JOIN pg_namespace n ON n.oid=cl.relnamespace
          WHERE c.contype='u' AND n.nspname NOT IN ('pg_catalog','information_schema','crdb_internal')
UNION ALL SELECT 'FOREIGN KEY constraints', count(*)::STRING FROM pg_constraint c
          JOIN pg_class cl ON cl.oid=c.conrelid JOIN pg_namespace n ON n.oid=cl.relnamespace
          WHERE c.contype='f' AND n.nspname NOT IN ('pg_catalog','information_schema','crdb_internal')
UNION ALL SELECT 'FKs with >1 column',    count(*)::STRING FROM pg_constraint
          WHERE contype='f' AND array_length(conkey,1)>1
UNION ALL SELECT 'FKs with 3 columns',    count(*)::STRING FROM pg_constraint
          WHERE contype='f' AND array_length(conkey,1)=3
ORDER BY 1;
```

**Do not count composite foreign keys through `information_schema.key_column_usage`.** On this
build a join on `constraint_name` alone cross-products and reports single-column FKs as
seven-column ones. `pg_constraint.conkey` is the correct source; the numbers above come from it.

### 8.2 The hybrid-retrieval `EXPLAIN` (§1), in full

```sql
EXPLAIN
SELECT c.cue_id::STRING AS id, 'lexical' AS arm FROM mainline.event_cue c
 WHERE c.tsv @@ to_tsquery('english','isolation')
UNION ALL
(SELECT e.cue_id::STRING, 'dense' FROM mainline.event_cue_embedding e
  WHERE e.site_id  = '00000000-0000-0000-0000-000000000001'::UUID
    AND e.scope_id = '00000000-0000-0000-0000-000000000001'::UUID
    AND e.facet    = 'body'
  ORDER BY e.emb <=> '[0.1, 0.1, … 1024 values …]'::VECTOR(1024) LIMIT 5);
```

Use `<=>` (cosine), not `<->`: the index is `vector_cosine_ops`, and `<->` produces
`ERROR: index "cue_scoped_idx" cannot be used for this query (SQLSTATE 42809)` — measured today,
and worth knowing before demonstrating this on camera.

### 8.3 Environment for every probe on this page

`cockroach sql --insecure -d mainline_demo` inside container `trappoint-crdb`,
**CockroachDB CCL v26.2.5** (x86_64-pc-linux-gnu, built 2026/07/28, go1.25.5), single node, all
probes run **2026-08-16** and re-run the same day (§10). The public origin reports the same build
string from `GET /v1/health`, together with `deploy_chain_applied 271` / `deploy_chain_files 271` —
re-derive both with one `curl`. The migration chain on disk is 271 files
(`ls verticals/mainline/db/migrations/*.sql | wc -l`), matching what the origin reports applied.
Scratch demonstrations ran in database `w_w5` on the same node;
**nothing in `mainline_demo` was written by this census** — every probe against it is a `SELECT`
or an `EXPLAIN`. It is a shared development cluster, so row counts in the append-only logs move
under other work; every count on this page is a count of *schema objects*, which do not.

`crdb_internal` is **refused** on this cluster with `42501` unless
`allow_unsafe_internals = true`, so every probe on this page uses `pg_catalog` and
`information_schema` only — which is also why they are all runnable by a reader with an ordinary
SQL login rather than an admin one.

---

## 9. WHAT W7 SHOULD TAKE, IN PRIORITY ORDER

Ranked by the plan's R5 — *store → retrieve → act* first, breadth last.

1. **The database computes the identity of a memory.** `blocking_check.dedupe_key`, generated
   `STORED`, `UNIQUE`, **served on the live URL and byte-identical to the local computation**
   (§0.2, §3.4). This is the strongest *Agentic Memory Design* row in this file: an agent that
   writes the same thing twice gets one row, and not because the agent was careful.
2. **The event log is a SHA-256 hash chain CockroachDB computes** (§3.1), and a `UNIQUE INDEX
   linear (permit_id, prev_seq)` makes the chain unforkable. Carry the precision: the column
   computes the digest, a trigger verifies the input (W6).
3. **Ask the live URL about a permit and it reads its own CHECK constraints out of the catalog**
   (§5.1) — name, predicate text, live counter values, reflected per request.
4. **Refusal as a missing row.** The three-column FK onto `subject_transition`, and the 21-of-24
   `clearance_legal` grid where `(blood_fatal, accept_residual)` simply is not there (§5.2). The
   referenced rows are served publicly.
5. **A uniqueness rule for a subset of rows.** `one_live_disposition`, `carriage_one_open`, and
   CockroachDB's `EXPLAIN` printing the words `(partial index)` (§4.1).
6. **R8's corrected hybrid claim** (§1) — 4 `VECTOR` columns, 3 `cspann` indexes, 1 generated
   `tsvector`, 5 inverted indexes, one `EXPLAIN` showing both arms.
7. **Seven enum types, all seven reachable in four public GETs** (§2), with declaration order as
   severity order.
8. Storage-layer craft, if there is room: column families isolating the 1024-dim vector,
   9 `STORING` indexes, `schema_locked` on all 89 tables, and **zero sequences on purpose** (§5.3,
   §5.4, §6).

**Three things W7 must not carry from this file:** expression indexes, hash-sharded indexes and
table partitioning. All three were audited today and all three are **zero** (§6).

---

## 10. VERIFICATION PASS — every number on this page re-measured, 2026-08-16

This page was written from probes and then **re-probed end to end by a second pass** on the same
day, against the same cluster and the same live origin. The point of recording it is that a judge
who reruns §8.1 should get the §0.1 table character-for-character, and three numbers on this page
moved when they were checked a second time. They are listed so nobody has to wonder which draft
they are reading.

**Re-measured and identical:** all 22 rows of the §0.1 census table; the 4 `VECTOR` columns and 1
`TSVECTOR` (R8); all 8 generated `STORED` columns with their expressions verbatim; 7 enum types /
36 labels; the 6 partial indexes verbatim; the 2 three-column FKs; the 5 GIN and 9 `STORING`
indexes; `schema_locked = true` on 89 of 89 tables; 461 CHECKs with 4 bare-`IS NOT NULL` and 0
auto-named; 18 legal transitions, 21-of-24 clearance pairs, `(blood_fatal, accept_residual)` absent;
0 FKs from `disposition` to `defeater_option` against 10 FKs on `disposition`; `mainline_api`'s 8
grant rows including `blocking_check` `SELECT,UPDATE` without `INSERT`.

**Re-measured against the live origin and identical:** `/v1/health` → 271/271, `v26.2.5`,
fingerprint `ec9b1ce7…`; `blocking_check.dedupe_key` → `c4bd7e3a…329c` from the URL and the same
64 hex characters from the cluster's generated column (§0.2); `head_seq: 2`; 7 reflected CHECK
constraints on the permit.

**Re-run and reproduced:** the hash chain (`matches = t` on both rows, `every_link_holds = t`); the
hybrid `EXPLAIN` with both arms and `prefix spans`; `EXPLAIN` printing the literal string
`(partial index)` on both `one_live_disposition` and `signing_credential_by_signer`; the `tsv`
inverted-filter plan; and all three scratch demonstrations — `23505` on the partial unique index,
`23505` on the generated `dedupe_key`, `23503` on the composite FK.

**Three corrections made by this pass**, each already applied above:

| § | was | now | why it moved |
|---|---|---|---|
| §4.4 | `DESC` key columns **18** | **16** | 16 under both `LIKE '% DESC%'` and a key-list-only match. 18 was not reproducible. |
| §6 | "48 defaulting to `now()`" | **48** bare `now()` + **1** `now() + '30 days'` | `ILIKE '%now()%'` returns 49; the detector now says which is meant. |
| §5.1 | "16 CHECKs of which 7 mention `'merged'`" | same 7 and 4, but the detector is now the **quoted** literal | An unquoted `%merged%` returns 8 and 5. The API filters on `"'merged'"` (`reads.py:360`); `permit_commit_sized` and `cr_commit_sized` are the near-misses. |

None of the three changes a claim the close block would make. The third is the one that mattered:
the numbers 7 and 4 were right, the stated way to check them was not, and a judge checking in under
a minute would have got 8 and 5 and concluded we had miscounted.

**Nothing was written to `mainline_demo` by either pass.** Every probe against it is a `SELECT`, an
`EXPLAIN`, or a catalog read. The three refusal demonstrations ran in scratch database `w_w5`
(created as `w_W5`; CockroachDB folds unquoted identifiers to lower case, so it is addressed as
`-d w_w5`). No AWS call, no deploy, no SSM write, no grant change, and no credential appears on
this page.
