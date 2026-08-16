<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# FEATURE CENSUS — the master

**Worker:** W7 (reconciliation) · **Date:** 2026-08-16 · **Deadline:** 2026-08-18 17:00 EDT
**Plan:** [`feature-census-plan.md`](feature-census-plan.md) — its eight rulings bind this page.
**Sources merged:** the six worker files under [`census/`](census/), the generated
`evidence/tool-usage/aws-services.json` and `evidence/tool-usage/crdb-features.json`,
`docs/TOOL-USAGE.md`, and [`MUST-NOT-CLAIM.md`](MUST-NOT-CLAIM.md).

This page is the single authority the film's closing block
([`census/close-block.md`](census/close-block.md)) and the Devpost text are written from. Every
row carries a state, a location, and a command a stranger can paste in under a minute together
with the first line that command prints. Where a claim cannot be settled without a credential or
an apply, the row says so instead of rounding up.

**Nothing on this page was produced by a deploy.** No `terraform apply`, no redeploy, no AWS API
call, no SSM write, no grant change, no credential read or printed, and no commit. The three
network calls this worker made are two unauthenticated HTTPS requests to the public demo origin
and nothing else (§8).

---

## 0. THE FIVE STATES (ruling R2), AND THE TWO CORRECTIONS APPLIED EVERYWHERE

The census uses the vocabulary `scripts/submission/capture_tool_evidence.py` already emits, so
this page and `evidence/tool-usage/*.json` cannot end up disagreeing in front of a judge.

| state | means | generator verdict |
|---|---|---|
| **LIVE** | it runs when a stranger sends one HTTP request to the demo origin | EXERCISED + a live-origin check |
| **REPO** | it ran, in this repository, with a committed artefact — and **not** in that request path | EXERCISED, no live-origin check |
| **APPLIED** | it exists in the AWS account, created by the real apply of 2026-08-14, and no request touches it | EXERCISED via a Terraform state or a console artefact |
| **DECLARED** | written and valid; **never created**, never run | DESIGNED |
| **NOT-AVAILABLE** | checked on this platform, absent, and no dependency taken | NOT-AVAILABLE |

**REPO is the Bedrock construction (ruling R4) and it reads as confidence, not hedging.** Amazon
Bedrock is real in this repository and is not in the demo's request path — the deployed Lambda
imports `psycopg` and nothing else, deliberately. Every REPO row on this page is phrased that way.

### R1 — the Managed MCP Server is DEMONSTRATED, and the number is 15 of 16

The premise that the CockroachDB Cloud Managed MCP Server is undemonstrated came from checking for
a *directory* and reading its absence as an absence of evidence. There are **two** committed
end-to-end transcripts against `https://cockroachlabs.cloud/mcp`, five days apart, and they agree:

```
evidence/deploy/judge-run.json   2026-08-11   15 / 16   DIVERGED — KNOWN GAP   credential_publishable false
evidence/mcp/pack-run.json       2026-08-16   15 / 16   DIVERGED — KNOWN GAP
evidence/mcp/session.json        sql_identity managed-mcp · server cockroachdb-cloud 1.0.0 · 12 tools · protocol 2025-06-18
```

Every document that names this tool carries **15 of 16**, the run's own verdict
`DIVERGED — KNOWN GAP`, and `credential_publishable: false`. The number is not rounded off and the
key is not published: its own tool list carries `create_database`, `create_table` and `insert_rows`.

### R8 — "5 live VECTOR columns" is wrong, and the true claim is stronger

Measured on the pinned local node today: **4 columns of SQL type `VECTOR`, plus 1 `TSVECTOR`.** The
old count reached five by counting the `tsvector` as a vector column. The corrected claim:

> **4 `VECTOR` columns across 4 tables, indexed by 3 `cspann` distributed vector indexes each of
> which must declare prefix columns — and, in the same schema, a generated `TSVECTOR` column with
> 5 inverted indexes beside it. Hybrid lexical-plus-dense memory in one database, with no second
> engine and no sync job.**

The fourth vector column (`event_cue_stage.emb`) is a staging table and carries no `cspann` index.
4 columns and 3 indexes is not an inconsistency; it is why the two numbers are quoted separately.

---

## 1. HOW TO CHECK ANY ROW ON THIS PAGE

Four commands cover most of the census. Each prints its expected first line.

```bash
# 1 — the live origin, no credential, no account          → ok=True … 271 / 271
curl -s https://ihuuyvm4z6nfuktihnkey77fpy0eyrhj.lambda-url.ap-southeast-1.on.aws/v1/health

# 2 — the four-beat gate run on that same origin           → verdict PROVEN, 4 beats
curl -s -X POST -H 'content-type: application/json' -d '{}' \
  https://ihuuyvm4z6nfuktihnkey77fpy0eyrhj.lambda-url.ap-southeast-1.on.aws/v1/demo/gate-run

# 3 — the schema census against the pinned local node      → one CSV row of counts
docker exec trappoint-crdb ./cockroach sql --insecure -d mainline_demo --format=csv -e "<probe>"

# 4 — the committed transcripts, no network at all
python -c "import json;d=json.load(open('evidence/mcp/pack-run.json'));print(d['passed'],'/',d['total'],d['verdict'])"
```

Run today, command 1 printed `ok True · CockroachDB CCL v26.2.5 · mainline_demo · 271 / 271 ·
schema_fingerprint ec9b1ce7…50339`; command 2 printed `verdict PROVEN, 4 beats, isolation
SERIALIZABLE, opened == closed logical timestamp, persistence_check.identical true`; command 4
printed `15 / 16 DIVERGED — KNOWN GAP`.

**Row shape** is the plan's §4 shape with one field added — `source:`, naming the worker file that
carries the full working, so that any row on this page can be traced to the desk that measured it.

---

## 2. THE MASTER CENSUS

Ordered by ruling **R5**: CockroachDB-as-memory first, because the Official Rules break ties
lexicographically and *Agentic Memory Design* is printed first. AWS breadth follows.

---

### 2.1 CockroachDB as a programmable, self-defending database

#### PL1 · PL/pgSQL stored functions

```
state:         LIVE
what it is:    26 PL/pgSQL functions run inside CockroachDB; the gate is a property of the
               write, not a service the agent calls before writing.
where:         verticals/mainline/db/migrations/*_fn_*.sql (26 files, one rendered object each)
               packages/trappoint-sql/refvertical/sql/0119a_fn_explain_refusal.sql
verify in 60s: cockroach sql -d mainline_demo -e "SELECT count(*) FROM pg_proc p JOIN pg_language l
               ON l.oid=p.prolang WHERE l.lanname='plpgsql' AND p.prokind='f';"   →  26
say this:      "Twenty-six PL/pgSQL functions run inside CockroachDB. The gate is not a service
               the agent calls before writing; it is a property of the write."
never say:     "The application validates the write." It does not, and the point is that it
               cannot be made to skip the validation.
source:        census/crdb-programmable.md R1
```

#### PL2 · PL/pgSQL stored procedures

```
state:         LIVE
what it is:    2 stored procedures; the demo's merge beat is a CALL, so the transaction boundary
               and the gate sit on the same side of the wire.
where:         verticals/mainline/db/migrations/*_proc_*.sql (2 files) — mainline.merge_permit
verify in 60s: POST /v1/demo/gate-run on the live origin; beat 2's `statement` field reads
               `CALL mainline.merge_permit(%s, %s, %s, %s, %s, %s, %s, %s)`  (observed today)
say this:      "The demo's merge beat is a CALL of a stored procedure. The transaction boundary
               and the gate live on the same side of the wire."
never say:     "Stored procedures are used for convenience." They are the transaction boundary,
               which is why the gate cannot be bypassed by reordering client statements.
source:        census/crdb-programmable.md R2
```

#### PL3 · Triggers — 39 objects over 59 (trigger, event) pairs

```
state:         LIVE
what it is:    39 trigger objects, every one FOR EACH ROW, welding the 26 functions to the
               tables. `information_schema.triggers` emits one row per (trigger, event), which
               is why the same schema reads 59 there and 39 in pg_trigger.
where:         verticals/mainline/db/migrations/*_trg_*.sql (39 files)
verify in 60s: SELECT count(*) FROM pg_trigger WHERE NOT tgisinternal;            →  39
               SELECT count(*) FROM information_schema.triggers;                  →  59
say this:      "Thirty-nine row-level triggers over twenty-six PL/pgSQL functions, covering 59
               trigger-event pairs. The rules are welded to the tables, so every writer meets
               them — including one that never read our code."
never say:     "59 triggers" flat. A judge who runs the obvious count gets 39 and reads the
               difference as inflation. Saying both numbers costs one clause.
source:        census/crdb-programmable.md R3 · §1.1
```

#### PL4 · `fn_refuse_mutation` — append-only, welded to 17 tables, refusing the superuser

```
state:         LIVE
what it is:    17 evidentiary tables carry a trigger that raises unconditionally on UPDATE and
               DELETE. Measured as `root`, the cluster superuser: both verbs refused with
               P0001, row count unmoved.
where:         verticals/mainline/db/migrations/0128*_trg_refuse_mutation*.sql (11 tables)
               plus 0145e / 0145f / 0149a / 0149b / 0149y / 0149z (6 more)
verify in 60s: SELECT p.proname, count(DISTINCT t.tgrelid) FROM pg_trigger t JOIN pg_proc p
               ON p.oid=t.tgfoid WHERE NOT t.tgisinternal AND p.proname='fn_refuse_mutation'
               GROUP BY 1;                                          →  fn_refuse_mutation | 17
say this:      "Seventeen evidentiary tables refuse UPDATE and DELETE from every writer,
               including the cluster superuser. Measured: root cannot edit a permit event."
never say:     "Nothing can alter the record." A role holding DDL can drop the trigger; what
               that costs the attacker is a different and smaller claim.
source:        census/crdb-programmable.md R4 · §1.2
```

#### PL5 · The hash-chain enforcement trigger

```
state:         LIVE
what it is:    a trigger verifies that each event's `prev_digest` is the real predecessor before
               the row lands. The digest itself is a generated column (SC2); this row is the
               guard that refuses a forged LINK.
where:         mainline.fn_permit_event_chain — verticals/mainline/db/migrations, *_trg_* band
verify in 60s: SELECT proname FROM pg_proc WHERE proname LIKE '%chain%';   → fn_permit_event_chain
say this:      "The event chain is verified by the database on every append. A forged link is
               refused by the relation, not by a background auditor."
never say:     "The database computes the chain" in this row's name — the digest is SC2's
               generated column; this row is the trigger that refuses a bad predecessor.
source:        census/crdb-programmable.md R5
```

#### PL6 · `trappoint.explain_refusal` — the refusal explains itself, from the same engine

```
state:         LIVE
what it is:    a PL/pgSQL function returning JSONB: the minimal unsatisfiable subset and the
               nearest admissible alternative, computed by the engine that produced the refusal.
               Where it has no decomposition it returns `not_computable` rather than inventing one.
where:         packages/trappoint-sql/refvertical/sql/0119a_fn_explain_refusal.sql
               called at verticals/mainline/apps/demo-api/src/mainline_demo_api/refusal.py:141
verify in 60s: POST /v1/demo/gate-run → beat 2 carries a populated `naa` (kind
               dispose_obligations, 5 legal kinds); beat 3 carries `diagnosis "none"`,
               `naa null`, `naa_reason "not_computable"`.  Both observed today.
say this:      "The database does not just refuse; it returns a structured reason set computed
               by the same engine that refused — and where it has no decomposition, it says so
               rather than inventing one."
never say:     "Every refusal comes back with a nearest admissible alternative." On the demo's
               strongest refusal — the projection-drift attack — it does not, and that is the
               interesting half.
source:        census/crdb-programmable.md R6
```

#### PL7 · The refusal ledger's own append-only guard

```
state:         REPO
what it is:    the only append-only guard in the schema that also polices INSERT: it rejects a
               refusal whose reason set is empty or names a fact family the schema cannot hold.
where:         mainline.fn_refusal_ledger_guard
verify in 60s: SELECT count(*) FROM mainline.refusal_ledger;   →  0   (the guard is installed;
               its INSERT arm has not fired on the measured cluster, and this row says so)
say this:      "The ledger of refusals is itself append-only, and it rejects a refusal whose
               reason set is empty or names a fact family the schema cannot represent."
never say:     "It has been exercised in the demo." The table holds zero rows.
source:        census/crdb-programmable.md R7
```

#### PL8 · Row-level security, and `FORCE` — the table refuses its own owner

```
state:         LIVE
what it is:    4 tables carry row-level security, all 4 FORCE it (which removes the owner's
               exemption), under 25 policies declared in one matrix file the test suite asserts
               the cluster against. 5 of the 25 are restrictive.
where:         verticals/mainline/db/migrations/*_policy_*.sql (25 files)
verify in 60s: SELECT count(*) FROM pg_class WHERE relrowsecurity;        →  4
               SELECT count(*) FROM pg_class WHERE relforcerowsecurity;   →  4
               SELECT count(*) FROM pg_policies;                          →  25
say this:      "Four tables carry row-level security and all four FORCE it, so the policy binds
               the table's own owner. Twenty-five policies, declared in one matrix file the test
               suite asserts the cluster against."
never say:     the sentence `claim_hygiene` MNC-01 bans by name — RLS is tenancy and least
               privilege, evaluated by the same server the cluster administrator owns. Against
               that principal the claim is tamper-evidence, not prevention.
source:        census/crdb-programmable.md R8
```

#### PL9 · The deliberate RLS exclusion, recorded inside the database

```
state:         LIVE
what it is:    two CDC source tables are deliberately excluded from RLS, and the reason is a
               comment stored in the database next to the table it governs — CockroachDB v26.2
               documents that CDC queries on RLS tables fail, and CDC messages are unfiltered.
where:         obj_description('mainline_ops.outbox'::regclass)
verify in 60s: SELECT obj_description('mainline_ops.outbox'::regclass);
               →  begins `NO ROW LEVEL SECURITY`
say this:      "Two tables are deliberately excluded from row-level security, and the reason is
               a comment stored in the database next to the table it governs."
never say:     "RLS is applied everywhere." Four tables, refused on two, absent from the rest
               for a stated reason. A blanket control is less credible than a scoped one.
source:        census/crdb-programmable.md R9
```

#### PL10 · The nine-role lattice, the public revokes and the privilege floor

```
state:         LIVE for the roles, the revokes, the floor and the covenant — all in the 271-file
               deploy chain.  The §4 table-privilege matrix is NOT applied on the deployed cluster.
what it is:    nine roles, none of which can log in, splitting the duties: the role that detects
               an obligation cannot create one, the role that creates one cannot dispose of it,
               and the role that certifies the books has no write path to them. The nine are the
               duty-separation lattice, and they are distinct by design from the two service
               logins — `mainline_api`, which the Lambda authenticates as, and `mainline_judge`,
               the read-only login this submission publishes to judges. Those two CAN log in and
               are not lattice members: the lattice is privilege containers reached by
               membership, so there is no credential whose theft yields a role.
where:         verticals/mainline/db/GRANTS.yaml; the 0180-band role migrations
verify in 60s: SELECT rolname, rolcanlogin FROM pg_roles WHERE rolname IN
               ('mainline_migrator','mainline_owner','agent_gate','agent_projector',
                'agent_recaller','svc_disposition','mainline_auditor','auditor_ro',
                'quality_assurance') ORDER BY 1;
               →  9 rows, `rolcanlogin` = `f` on every one   (run 2026-08-16; output below)
say this:      "Nine roles, none of which can log in, split the duties: the role that detects an
               obligation cannot create one, the role that creates one cannot dispose of it, and
               the role that certifies the books has no write path to them."
never say:     "The grant matrix is applied on the deployed cluster." The roles and the revokes
               are; the table-privilege rows are not.
               "Every role whose name starts with `mainline` is NOLOGIN," and never publish a
               `LIKE` prefix-match on that name as the check. Measured 2026-08-16, a prefix-match
               returns **five** rows and **two of them CAN log in** — `mainline_api` and
               `mainline_judge`, the login this submission hands judges. Only the nine-name IN
               list above returns the lattice; a `LIKE` match on `agent_` returns **10**.
source:        census/crdb-programmable.md R10
```

Run on 2026-08-16 against the pinned local node
(`docker exec trappoint-crdb ./cockroach sql --insecure -d mainline_demo --format=csv`), that
query printed exactly nine rows:

```
rolname,rolcanlogin
agent_gate,f
agent_projector,f
agent_recaller,f
auditor_ro,f
mainline_auditor,f
mainline_migrator,f
mainline_owner,f
quality_assurance,f
svc_disposition,f
```

**The answer did not change; the command beside it did.** The predicate published here until
2026-08-16 was a `LIKE` prefix-match on the `mainline` name, introduced when the worker file was
merged upward. It returns five rows, with `rolcanlogin` true on `mainline_api` and
`mainline_judge` — so the published check refuted the published answer, using the very login a
judge is handed. **The claim was right and is kept at nine; only the check moved**, and it is now
the one that produces it, preserved verbatim from `census/crdb-programmable.md:827`. It is not
reprinted anywhere on this page, so it cannot be pasted back in by accident.

#### PL11 · Recursive CTEs

```
state:         REPO
what it is:    4 executable `WITH RECURSIVE` sites; the blame closure is computed by one that
               feeds its own INSERT — a single statement walks the ancestry DAG and writes the
               summary.
where:         verticals/mainline/db/queries/closure_write.sql:152
               registry/sql.py:57 (ANCESTRY_SQL) · diachronic/origin.py:133
verify in 60s: grep -rn "^WITH RECURSIVE" verticals/mainline/db/queries verticals/mainline/packages
               →  4 sites  (anchored, so the 5 prose mentions are excluded)
say this:      "The blame closure is computed by a recursive CTE that feeds its own INSERT —
               one statement walks the ancestry DAG and writes the summary."
never say:     "0034_event_edge.sql contains a recursive CTE." Its `WITH RECURSIVE` is inside a
               comment block. The correction is in the over-claim list (§5, O9).
source:        census/crdb-programmable.md R11 · §1.3
```

#### PL12 · Guarded `RETURNING` as a compare-and-swap

```
state:         LIVE
what it is:    the merge is a compare-and-swap: the UPDATE names the head sequence it expects and
               RETURNING proves it landed. On CockroachDB `GET DIAGNOSTICS ROW_COUNT` is
               unimplemented, so `RETURNING … INTO` is how a PL/pgSQL procedure detects a
               zero-row UPDATE at all.
where:         verticals/mainline/apps/demo-api/src/mainline_demo_api/transitions.py:838
               verticals/mainline/db/migrations/0117*, 0118* (RETURNING … INTO, 2 sites)
verify in 60s: grep -n "RETURNING" verticals/mainline/apps/demo-api/src/mainline_demo_api/transitions.py
               →  one hit, at :838
say this:      "The merge is a compare-and-swap: the UPDATE names the head sequence it expects
               and RETURNING proves it landed — which on CockroachDB is not a style choice,
               because GET DIAGNOSTICS ROW_COUNT is unimplemented."
never say:     "RETURNING is used throughout." There is exactly one in the live request path.
source:        census/crdb-programmable.md R12
```

---

### 2.2 CockroachDB schema, type and index features

#### SC1 · 7 user-defined enum types, 36 labels

```
state:         LIVE
what it is:    seven of the schema's vocabularies are enum types, not strings, declared in
               migrations 0010–0016, with declaration order as severity order.
where:         verticals/mainline/db/migrations/0010*.sql … 0016*.sql
verify in 60s: SELECT count(*) FROM pg_type t JOIN pg_enum e ON e.enumtypid=t.oid;   →  36
say this:      "Seven of this schema's vocabularies are CockroachDB enum types, not strings. All
               thirty-six labels are declared in migrations, and every one of the seven types
               has a label you can read in a response from the public demo URL."
never say:     "the enums are validated in the API" — they are validated by the type; the API
               never sees an invalid label. Adding a label is a schema change, not a config flag.
source:        census/crdb-schema-and-index.md §2
```

#### SC2 · Generated `STORED` columns — 8, and three of them are the story

```
state:         LIVE
what it is:    8 generated STORED columns. Two of them compute a SHA-256 hash chain:
               `permit_event.chain_digest` and `cr_event.chain_digest` are
               `GENERATED ALWAYS AS (digest(prev_digest || payload, 'sha256')) STORED`, so the
               application inserts the payload and the previous link and is structurally
               incapable of choosing the digest.
where:         verticals/mainline/db/migrations — permit_event / cr_event definitions
verify in 60s: SELECT count(*) FROM information_schema.columns WHERE is_generated='ALWAYS'; → 8
say this:      "The permit's event log is a SHA-256 hash chain, and CockroachDB computes it. The
               column is GENERATED ALWAYS AS (digest(prev_digest || payload, 'sha256')) STORED —
               the application inserts the payload and cannot choose the digest."
never say:     "the live URL serves chain_digest" — no declared route returns the column; what
               the origin serves is `head_seq`, the chain's length. And never say the generated
               column makes the log tamper-proof: it makes the digest unforgeable *given the
               inputs*; verifying the predecessor is PL5's trigger.
source:        census/crdb-schema-and-index.md §3.1 · §3.2
```

#### SC3 · `event_cue.tsv` — full-text search as a column definition

```
state:         REPO
what it is:    the lexical half of retrieval is a generated column: `to_tsvector('english',
               cue_text)` is the column's definition, so the search index cannot fall behind
               the text.
where:         mainline.event_cue.tsv
verify in 60s: SELECT count(*) FROM information_schema.columns WHERE data_type='tsvector'
               AND is_generated='ALWAYS';    →  1
say this:      "The lexical half of retrieval is a generated column — `to_tsvector('english',
               cue_text)` is the definition, so the index cannot fall behind the text, and it
               sits in the same schema, the same transaction and the same backup as the dense
               vectors."
never say:     "the demo searches text at the live URL." `mainline.event_cue` carries no grant
               to `mainline_api` at all, so no anonymous request reaches it.
source:        census/crdb-schema-and-index.md §3.3 · §1
```

#### SC4 · `blocking_check.dedupe_key` — the database computes the identity of a memory

```
state:         LIVE
what it is:    a generated STORED SHA-256 over the row's own contents, UNIQUE. An agent that
               writes the same obligation twice gets one row — and not because the agent was
               careful. The value is served on the live URL and is byte-identical to the local
               computation.
where:         mainline.blocking_check.dedupe_key + its UNIQUE index
verify in 60s: GET /v1/permits/{permit_id}/blocking-checks on the live origin returns
               `dedupe_key` — the same 64 hex characters the cluster's generated column holds
say this:      "An agent that writes the same obligation twice — because it crashed, retried, or
               simply did not remember — creates one row. Not because the agent is careful:
               because the identity of the row is a SHA-256 the database computes from the row's
               own contents, and it is UNIQUE."
never say:     "the live demo shows the duplicate being refused." It does not: `mainline_api`
               holds SELECT and UPDATE on that table and not INSERT — the standing
               `materialise_checks` / `exposure_receipt` gap the founder has not closed. The
               refusal is demonstrated on a cluster, not through the URL.
source:        census/crdb-schema-and-index.md §3.4 · §3.5
```

#### SC5 · `identity_assignment.descendant_key` — a generated column inside a PRIMARY KEY

```
state:         REPO
what it is:    "this ancestor clause has no descendant" is a fact that has to be unique, and
               NULL is not unique to NULL — so the key is COALESCE of the nullable UUID with a
               zero UUID, NOT NULL, in the primary key.
where:         mainline.identity_assignment
verify in 60s: SELECT indexdef FROM pg_indexes WHERE indexdef ILIKE '%descendant_key%';
say this:      "'This ancestor clause has no descendant' is a fact that has to be unique, and
               NULL is not unique to NULL. So the key is a generated column."
never say:     "descendant_clause_uuid is NOT NULL." It is nullable — that is the entire point,
               and a CHECK on the same table depends on it staying nullable.
source:        census/crdb-schema-and-index.md §3.6
```

#### SC6 · 6 partial indexes, used as invariants

```
state:         REPO  (one of the six, signing_credential_by_signer, is on a live-granted table)
what it is:    six indexes carry a WHERE clause and two of them are UNIQUE. A partial unique
               index is a uniqueness rule that applies to a subset of rows: a permit may
               accumulate any number of retracted clearances and at most one live one.
where:         one_live_disposition, carriage_one_open, signing_credential_by_signer, +3
verify in 60s: SELECT count(*) FROM pg_indexes WHERE indexdef ILIKE '%WHERE%';   →  6
               and `EXPLAIN` over the table prints the literal words `(partial index)`
say this:      "Six of this schema's indexes carry a WHERE clause and two are UNIQUE. A partial
               unique index is a uniqueness rule for a subset of rows — at most one live
               clearance per permit, any number of retracted ones. There is no application code
               in that sentence."
never say:     "we validate that there is only one live disposition." Nothing validates it. The
               index makes a second one unrepresentable.
source:        census/crdb-schema-and-index.md §4.1
```

#### SC7 · 5 inverted (GIN) indexes, one of them a trigram index

```
state:         REPO
what it is:    array containment for blame ancestry, a trigram index for substring search over
               clause text, and a GIN index over the generated tsvector — lexical and dense
               retrieval in the same database.
where:         pg_indexes, `USING gin`
verify in 60s: SELECT count(*) FROM pg_indexes WHERE indexdef ILIKE '%USING gin%';   →  5
say this:      "Five inverted indexes sit beside the vector indexes: array containment for blame
               ancestry, a trigram index over clause text, and a GIN index over the generated
               tsvector."
never say:     "the trigram index is chosen for our text queries." On the demo corpus the
               optimizer does not choose it, and the measured note says so.
source:        census/crdb-schema-and-index.md §4.2
```

#### SC8 · 9 `STORING` (covering) indexes — a CockroachDB-specific clause

```
state:         REPO
what it is:    nine secondary indexes carry the columns the read needs, so the answer comes out
               of one index. The refusal ledger's own index stores the constraint name, the
               SQLSTATE and the diagnosis.
where:         pg_indexes, `STORING`
verify in 60s: SELECT count(*) FROM pg_indexes WHERE indexdef ILIKE '%STORING%';   →  9
say this:      "Nine secondary indexes use CockroachDB's STORING clause to carry the columns the
               read needs — the refusal ledger's index stores the constraint name, the SQLSTATE
               and the diagnosis, which are the three things you ask for when you ask why the
               database said no."
never say:     "we measured the round-trip saving." No such measurement exists in this tree.
source:        census/crdb-schema-and-index.md §4.3
```

#### SC9 · 461 CHECK constraints — and the live origin reads them out of the catalog

```
state:         LIVE
what it is:    the API reflects the CHECK constraints that would refuse a permit — name,
               predicate text and the current value of each counter the predicate mentions —
               read from `pg_constraint` at request time. A constraint added by a future schema
               change appears in the response with no code change.
where:         verticals/mainline/apps/demo-api/src/mainline_demo_api/reads.py:340-360
verify in 60s: GET /v1/permits/{permit_id} on the live origin → 7 reflected CHECK constraints
               SELECT count(*) FROM pg_constraint WHERE contype='c';   →  461
say this:      "Ask the live URL about a permit and it answers with the predicates of the CHECK
               constraints that would refuse to issue it, read out of pg_constraint at request
               time. Nothing in the API knows those constraints in advance."
never say:     "the API documents the constraints." It reflects them — that is the claim worth
               making and it is the checkable one.
source:        census/crdb-schema-and-index.md §5.1
```

#### SC10 · 107 foreign keys, 19 composite, 2 of them three-column

```
state:         REPO for the constraint; LIVE for the referenced rows, which the origin serves
what it is:    the permit state machine is a three-column foreign key. Eighteen transitions are
               legal across two subject kinds out of the ninety-eight the alphabet permits, and
               the other eighty are not forbidden by a rule — they are absent from a table. An
               event claiming one is refused with 23503 by referential integrity.
where:         mainline.legal_edge · mainline.cr_legal_edge · mainline.subject_transition
verify in 60s: SELECT count(*) FROM pg_constraint WHERE contype='f'
               AND array_length(conkey,1)>1;   →  19
say this:      "The permit state machine is a three-column foreign key. Eighteen transitions are
               legal; the rest are not forbidden by a rule — they are absent from a table."
never say:     "the state machine is validated in code." The application never checks the edge.
source:        census/crdb-schema-and-index.md §5.2
```

#### SC11 · 3 tables split into COLUMN FAMILIES

```
state:         REPO
what it is:    the 1024-dimension embedding lives in its own column family, so scanning
               embedding metadata does not pull four kilobytes of floats per row off disk.
where:         verticals/mainline/db/migrations/0030_clause_band.sql:35 and two others
verify in 60s: grep 'FAMILY ' over `SHOW CREATE ALL TABLES`   →  3 tables
say this:      "The 1024-dimension embedding lives in its own CockroachDB column family, so
               scanning embedding metadata does not pull four kilobytes of floats per row."
never say:     "column families make our vector search faster." Nothing in this tree measures
               that. The claim is that the storage layout is declared, and it is.
source:        census/crdb-schema-and-index.md §5.3
```

#### SC12 · `WITH (schema_locked = true)` on all 89 base tables

```
state:         REPO
what it is:    every base table declares schema_locked, telling the cluster not to expect
               changes between deploys.
where:         SHOW CREATE ALL TABLES
verify in 60s: count of `schema_locked = true` == count of base tables   →  89 == 89
say this:      "Every one of the 89 base tables is declared WITH (schema_locked = true). A schema
               this project treats as a specification is one the cluster is told not to expect
               changes to."
never say:     "schema_locked prevents a schema change." It does not; the deploy chain unlocks
               and relocks. It declares intent between deploys.
source:        census/crdb-schema-and-index.md §5.4
```

---

### 2.3 CockroachDB transaction, isolation and time semantics

#### TX1 · `SERIALIZABLE`, set explicitly on every gate transaction

```
state:         LIVE
what it is:    every transaction this project opens against a subject issues SET TRANSACTION
               ISOLATION LEVEL SERIALIZABLE as its first statement, and the demo endpoint
               reports the level it ran at in its own response body. The four beats — a read,
               two refusals and an admitted write — run inside ONE transaction that is rolled
               back, proven by `opened_logical_timestamp == closed_logical_timestamp` and by a
               before/after row-count fingerprint taken outside it.
where:         gate_run.py:603 · cr_gate_run.py:572 · transitions.py:459 · gate.py:56
verify in 60s: POST /v1/demo/gate-run → `transaction.isolation` reads `SERIALIZABLE`; both
               logical timestamps identical; `persistence_check.identical` true.  Observed today:
               opened == closed == 1786880349703314809.0000000000, identical true.
say this:      "The demo runs four beats — a read, two refusals and an admitted write — inside
               one SERIALIZABLE transaction that is then rolled back, and the response tells you
               the isolation level, the two logical timestamps that prove it was one
               transaction, and the savepoints, so you never have to take our word for it."
never say:     "CockroachDB is serializable so we get this for free." The level is set
               explicitly on every attempt — and TX3 is the measurement of what is lost one
               level down.
source:        census/crdb-transactional.md §2.1
```

#### TX2 · `SQLSTATE 40001` — retried, and classified as undecided rather than failed

```
state:         LIVE (the loop is in the request path of all five POSTs) · REPO for the proof it fires
what it is:    40001 is the only SQLSTATE this project retries; it retries the whole transaction
               from BEGIN, and calls the outcome *undecided* rather than *failed*, because the
               database aborted it — so nothing was written and nothing was decided.
where:         verticals/mainline/apps/demo-api/src/mainline_demo_api/db.py:154 · retry.py
               evidence/deploy/cloud-contention.json
verify in 60s: grep -n "40001" .../mainline_demo_api/db.py    →  the single retried code
say this:      "40001 is the only code we retry, we retry the whole transaction rather than a
               statement, and we call it undecided rather than failed. Twelve induced races on
               the managed cluster and twelve on a local node each produced RETRY_SERIALIZABLE
               at commit and the loop recovered every one; when the budget is spent the caller
               gets 503 transaction_undecided carrying sqlstate 40001 — never a refusal, because
               the gate never got to say anything."
never say:     that the deployed function's retry loop has been observed firing in production.
               It has not; proving it needs induced contention against the live origin.
source:        census/crdb-transactional.md §2.2
```

#### TX3 · `READ COMMITTED` — shipped as a contrast, and measured today

```
state:         REPO for the isolation downgrade (exercised today) · DECLARED for the conformance
               case, which cannot build its world on the deployed schema
what it is:    the same two-connection crossed history, run six times at each of two isolation
               levels on the same node in one sitting. SERIALIZABLE refused it 6 of 6 with
               40001; READ COMMITTED admitted it 6 of 6. And `cluster_logical_timestamp()` —
               the witness the gate relies on — is refused with 0A000 at the weaker level.
where:         packages/trappoint-conformance/cases/cf45_read_committed.py
               census/crdb-transactional.md §7.1 (the script, in full)
verify in 60s: run that script against the local node; it prints
               `SERIALIZABLE : 40001 in 6 of 6 crossed races` then
               `READ COMMITTED  : 40001 in 0 of 6 crossed races`
say this:      "The history CockroachDB refuses to order at SERIALIZABLE is one it silently
               admits one level down. Six of six, and zero of six, in one paste. That is why the
               memory layer is a database and not a cache."
never say:     anything of the form "the conformance suite runs" — that case is one of the 46
               blocked by a single missing column, and the project's own census prints the number.
source:        census/crdb-transactional.md §1 · §2.3
```

#### TX4 · `AS OF SYSTEM TIME` — used, and then proved unable to reach

```
state:         REPO
what it is:    the project uses time-travel reads where they work and ships a case whose whole
               purpose is to show where they stop — the same query returns three rows at five
               seconds ago and two at ten seconds ago, and ninety days ago is refused by the
               replica GC threshold, with `gc.ttlseconds = 4500` read off the cluster in the
               same run. The evaluation harness then refuses to execute any SQL string
               containing `AS OF SYSTEM TIME`.
where:         packages/trappoint-conformance/cases/cf46_time_travel_cannot_reach.py:106
               packages/trappoint-recall/src/trappoint_recall/eval/splits.py
verify in 60s: run census/crdb-transactional.md §7.2's script; it prints the three-row and
               two-row readings and the refusal at the horizon
say this:      "We use AS OF SYSTEM TIME, and then we ship the case that proves it cannot do the
               thing people assume. Long-horizon history is the application-level commit DAG,
               not MVCC — so our evaluation harness refuses outright to execute any SQL
               containing the clause."
never say:     "4 hours" for the retention. The cluster says 4500 seconds; a source file's
               refusal message still prints 14400 and is generous by a factor of 3.2 in the
               direction that understates our own case (escalation E-Q1, §7).
source:        census/crdb-transactional.md §2.4 · §3 C3
```

#### TX5 · Follower reads — confirmed, not downgraded

```
state:         REPO
what it is:    the fixity patrol and coverage scans read at `AS OF SYSTEM TIME
               follower_read_timestamp()`, so a background integrity sweep can never contend
               with a merge. The rule is written as a prohibition in both directions.
where:         verticals/mainline/db/migrations/0180c_role_agent_patroller.sql:37
               tests/integration/fixity/test_fixity_cluster.py
verify in 60s: pytest tests/integration/fixity/test_fixity_cluster.py -q --junitxml
               →  today: tests=3 failures=0 errors=0 skipped=2
say this:      "Background integrity patrols read at follower_read_timestamp() so an integrity
               sweep can never contend with a merge, and the rule is written both ways: patrol
               reads must be follower reads, gate reads must never be."
never say:     "follower reads serve the demo." They do not.
source:        census/crdb-transactional.md §2.5 · §3 C2
```

#### TX6 · `crdb_internal` — one existing row that is two opposite facts

```
state:         NOT-AVAILABLE for the `crdb_internal` schema (restricted by platform default on
               v26.2.5, SQLSTATE 42501) · LIVE for the unqualified HLC builtin
what it is:    the hybrid-logical clock reading that proves the four beats shared one
               transaction is `cluster_logical_timestamp()`, unqualified. The qualified spelling
               returns 42883 unknown function. No live path touches the `crdb_internal` schema.
where:         gate_run.py:374 (the builtin) · packages/mainline-mcp/.../limits.py:75 (the
               schema, on the MCP identity's forbidden list)
verify in 60s: grep -rn "crdb_internal" verticals/mainline/apps/demo-api/src/   →  no output
say this:      "The hybrid-logical clock is live in the demo's request path — it is what proves
               the four beats shared one transaction — and it is an unqualified builtin, not a
               `crdb_internal` call. The schema itself is refused with 42501 on this version
               unless a session explicitly opts in, which is why our audit views are the API
               rather than a bypass around one."
never say:     "we use `crdb_internal` for the HLC ordering the ledger." The qualified function
               does not exist. This sentence is in `DEVPOST.md:124` today — over-claim O3, §5.
source:        census/crdb-transactional.md §2.6 · §3 C1
```

#### TX7 · CHANGEFEED — declared, and the reason is good engineering

```
state:         DECLARED  (generator verdict DESIGNED)
what it is:    `CREATE CHANGEFEED` is written, discussed, and deliberately never run. Changefeeds
               are cluster jobs rather than schema, so one inside a deploy step makes that step
               non-idempotent across environments and couples DDL to a sink credential.
where:         packages/trappoint-migrate/README.md:253 — the migrator refuses them, in writing
verify in 60s: SHOW CHANGEFEED JOBS;   →  zero rows
say this:      "Changefeeds are designed and deliberately not run — they are cluster jobs rather
               than schema, and the migrator refuses them for that reason in writing.
               SHOW CHANGEFEED JOBS on our cluster returns zero and we would rather say so."
never say:     "we stream memory updates with CDC", or anything implying a live feed.
source:        census/crdb-transactional.md §2.7
```

#### TX8 · `SAVEPOINT` / `ROLLBACK TO SAVEPOINT`

```
state:         LIVE
what it is:    each beat expected to be refused runs inside its own savepoint, so a CHECK
               violation undoes that beat without poisoning the transaction the next beat needs.
               Without it, four-beats-in-one-transaction is impossible: in PostgreSQL wire
               semantics a statement after an aborted one is 25P02.
where:         verticals/mainline/apps/demo-api/src/mainline_demo_api/gate_run.py:671
verify in 60s: POST /v1/demo/gate-run → the response names the savepoints alongside the two
               identical logical timestamps
say this:      "Two of the four beats are refusals, and a refusal aborts a PostgreSQL
               transaction. Each refusable beat therefore runs inside its own savepoint, which
               is how four beats fit inside one transaction that reports a single logical
               timestamp at both ends."
never say:     the savepoints hide or suppress a refusal. Each refusal's SQLSTATE and constraint
               name are in the response; the savepoint scopes the undo.
source:        census/crdb-transactional.md §2.8
```

#### TX9 · No advisory locks — so the migration lease is a row

```
state:         REPO
what it is:    `pg_advisory_lock` does not exist in CockroachDB and every PostgreSQL migration
               tool assumes it, so this project's migrator holds its lease in a real table with
               a holder and an expiry. It waits for expiry rather than stealing, and the
               takeover is a conditional UPDATE the database evaluates.
where:         packages/trappoint-migrate/src/trappoint_migrate/lock.py:5 · trappoint.schema_lock
verify in 60s: SELECT * FROM trappoint.schema_lock;   →  the lease row, holder and expiry
say this:      "CockroachDB has no advisory locks, so our migrator holds its lease as a row with
               an expiry — a crashed migrator leaves a lease that is visible and inspectable
               instead of a mutex that silently vanished. And DDL is attempted exactly once,
               ever, because a CockroachDB schema change is a background job."
never say:     that the lease can be stolen or that a retry loop guesses whether DDL landed.
source:        census/crdb-transactional.md §2.9
```

#### TX10 · The version pin, served publicly

```
state:         LIVE
what it is:    CockroachDB **CCL v26.2.5** is pinned; the local container and the deployed origin
               report the identical build string, and the origin serves it to anyone with no
               credential, beside the 271-of-271 deploy-chain count and the schema fingerprint.
where:         GET /v1/health on the live origin
verify in 60s: curl -s $ORIGIN/v1/health  →  cluster_version
               "CockroachDB CCL v26.2.5 (x86_64-pc-linux-gnu, built 2026/07/28 18:56:00, go1.25.5)"
say this:      "Our CockroachDB version is not a claim in a README — a judge reads it out of the
               live origin in one unauthenticated request, together with the deploy-chain count
               and the schema fingerprint, and it is the same build string as the container we
               measure against."
never say:     the version without `CCL`, which is what the build actually reports. And read
               `deploy_chain_applied` as the chain ledger's own count on the database that
               request reached — re-derived per request, never quoted from memory.
source:        census/crdb-transactional.md §2.10 · census/aws-live-path.md §1.2
```

#### TX11 · Multi-region shape — stated honestly, because it is not used

```
state:         NOT-AVAILABLE
what it is:    this project uses no CockroachDB multi-region feature. Not SET PRIMARY REGION,
               not ADD REGION, not REGIONAL BY ROW, not REGIONAL BY TABLE, not GLOBAL, not
               SURVIVE … FAILURE.
where:         nowhere — zero hits is the finding
verify in 60s: SHOW DATABASES;   →  `primary_region` NULL
say this:      "We do not claim multi-region. The cluster is CockroachDB Cloud Basic in
               ap-southeast-1, one region, and the local node we measure against is a single
               node with an empty locality. What we claim is the isolation and retry contract,
               which is the part of the distributed story a single node can prove."
never say:     anything about a replica outside ap-southeast-1.
source:        census/crdb-transactional.md §2.11
```

---

### 2.4 The four contest-named CockroachDB tools

The Official Rules name four and require at least two. **Four are named here; three are exercised
with a committed transcript and the fourth is shipped and not evidenced** — which, with the floor
at two, is a margin stated rather than a count inflated. None of the four is LIVE under R2: the
live origin's request path opens a `psycopg` connection and reads SSM; it does not call MCP, does
not run an ANN query, does not shell out to `ccloud` and does not load a skill. What the first
three carry instead is a transcript against the real managed cluster, which is a stronger artefact
than a code path a judge cannot see.

**This is the block the film's closing card `k3` prints from, and the four lines on that card
resolve here, row for row.** Nothing is on the card that is not measured in this section, and no
row on the card is in a better state than its row below.

| what `k3` prints | the row it resolves to | the state on both |
|---|---|---|
| `Distributed Vector Indexing (C-SPANN)  EXERCISED  3 cspann, 4 VECTOR, 42809  evidence/aws/ann/` | **CT2** | REPO = EXERCISED |
| `Managed MCP Server  EXERCISED  15 of 16, DIVERGED, published  evidence/mcp/` | **CT1** | REPO = EXERCISED |
| `CockroachDB Cloud + ccloud CLI  EXERCISED  cluster list -o json, parsed  evidence/ccloud/` | **CT3** | REPO = EXERCISED |
| `CockroachDB Agent Skills  DESIGNED  shipped, validated; NO RUN IS COMMITTED  skills/` | **CT4** | **DESIGNED** |

The four one-line checks a judge can paste from that same frame, each with the first line it
actually printed here on 2026-08-16, are in
[`census/crdb-four-tools.md` §0.1](census/crdb-four-tools.md).

#### CT1 · CockroachDB Cloud Managed MCP Server

```
state:         REPO   (ruling R1 — DEMONSTRATED, twice, five days apart)
what it is:    CockroachDB Cloud's own hosted MCP endpoint, driven over Streamable HTTP with a
               service-account key and an `mcp-cluster-id` header pinning one cluster; a
               16-question pack run through it end to end.
where:         evidence/mcp/ (session.json · tools-schema.json · pack-run.json · README.md)
               evidence/deploy/judge-run.json → channels.mcp   (the 2026-08-11 run)
               verticals/mainline/demo/judge/runner.py::run_via_mcp
verify in 60s: python -c "import json;d=json.load(open('evidence/mcp/pack-run.json'));
               print(d['generated_at'],d['passed'],'/',d['total'],d['verdict'])"
               →  2026-08-16T07:33:46Z 15 / 16 DIVERGED — KNOWN GAP     (observed today)
say this:      "We drove CockroachDB Cloud's Managed MCP Server end to end against our own
               cluster — protocol 2025-06-18, server cockroachdb-cloud 1.0.0, twelve tools — and
               put a sixteen-question pack through it. Fifteen of sixteen. The one that failed is
               recorded, not rounded off, and we do not publish that key, because its own tool
               list can create a database."
never say:     "Judges can query our ledger over MCP." (`credential_publishable` is false; judges
               get the read-only `mainline_judge` pgwire login instead.)
               "The MCP pack passes." (It exits 1. 15 of 16, verdict DIVERGED — KNOWN GAP.)
               "Our MCP integration is read-only." The *endpoint* is not; our *client* is, and
               the enforcement is an httpx request hook that raises before transmission.
source:        census/crdb-four-tools.md §1
```

Two facts travel with this row and neither may be dropped: the one failure (`N01`) is that the
`managed-mcp` identity reads a `mainline_qa` view the pack asserted it could not, and the
published `mainline_judge` login refuses the same statement at 42501 — the credential a judge is
actually given is the tighter of the two, which does not convert the failure into a pass and is
not scored as one. Closing it means changing a grant on submission eve; escalated, not done (§7).

#### CT2 · CockroachDB Distributed Vector Indexing

```
state:         REPO
what it is:    3 `cspann` distributed vector indexes over 1024- and 256-dimension embeddings,
               each with mandatory prefix columns that select which K-means tree is searched.
               C-SPANN keeps a separate tree per distinct prefix value, so the prefix rule is a
               correctness surface and not a performance knob — and the server enforces it.
where:         verticals/mainline/db/migrations/0031_clause_embedding.sql:149 (ce_ann)
               + cue_scoped_idx, cue_sweep_idx
               evidence/aws/ann/ (ann-proof.json · explain-hinted.txt · explain-unhinted.txt)
               skills/designing-vector-recall-prefixes/  (the rule, written down)
verify in 60s: SELECT count(*) FROM pg_indexes WHERE indexdef ILIKE '%cspann%';   →  3
               grep -n "prefix spans" evidence/aws/ann/explain-hinted.txt          →  line 67
say this:      "Recall is a C-SPANN distributed vector index inside the same database that holds
               the gate, so retrieval and refusal share one transaction domain. Every prefix
               column must be bound to a single value or CockroachDB refuses the query outright
               — SQLSTATE 42809 — and we ship that refusal as evidence, not as a comment."
never say:     "The demo does an ANN search when you click it." No ANN query runs in the demo's
               HTTP request path; the indexes are live in the database and the search is
               evidenced under evidence/aws/ann/ and over MCP (Q10 / Q10C).
               "The optimizer needs our hint." That counterfactual did not reproduce, and the
               artefact records `gt06_counterfactual_reproduces: false` rather than dropping it.
source:        census/crdb-four-tools.md §2 · combine with SC3 and §0 R8 for the hybrid claim
```

#### CT3 · ccloud CLI (Agent-Ready)

```
state:         REPO
what it is:    CockroachDB Cloud's first-party CLI driven with `-o json`, so the committed
               transcript is parsed rather than screen-scraped.
where:         evidence/ccloud/cluster-list.txt · evidence/ccloud/README.md:37
verify in 60s: python -c "import json;t=open('evidence/ccloud/cluster-list.txt',encoding='utf-8')
               .read();c=json.loads(t[t.index('['):])[0];print(c['name'],c['cockroach_version'],
               c['cloud_provider'],c['regions'][0]['name'])"
               →  mainline-dev v26.2.5 AWS ap-southeast-1
say this:      "We use the ccloud CLI with -o json and parse it — the committed transcript is
               machine-readable, and the cluster id in it is the same one our MCP session pins.
               We also state the limit we hit: ccloud 0.6.12 has no non-interactive
               service-account auth, so headless paths use the Cloud REST API with the same key."
never say:     "Our agent drives ccloud." It cannot, from a cold start, on 0.6.12 — measured.
               And no automated lane has ever pointed at the managed cluster; the transcript is
               a human session.
source:        census/crdb-four-tools.md §3
```

#### CT4 · CockroachDB Agent Skills Repo (Open Source)

```
state:         DESIGNED — the generator's verdict, kept, and the word the film's `k3` card
               prints. **This row is NOT REPO.** REPO means "it ran, in this repository, with a
               committed artefact"; no run of either assertion script is captured under
               `evidence/`. The skills are shipped and not evidenced. An earlier draft of this
               census promoted this row to REPO on the strength of a CI lane; the promotion is
               withdrawn here — see U-C4 in §4, which now proposes the detector without
               asserting the state.
what it is:    two authored Agent Skills for building database-enforced refusals, published
               under Apache-2.0 through both the Agent Skills spec and a Claude Code plugin
               marketplace, each shipping a script that FAILS when the guarantee does not hold.
               A third is de-branded and staged for contribution, and not filed.
where:         skills/designing-diachronic-gates/ · skills/designing-vector-recall-prefixes/
               skills/validate-spec.py · .github/workflows/skills.yml · .claude-plugin/marketplace.json
verify in 60s: python -c "import json;print(json.load(open('evidence/tool-usage/
               crdb-features.json'))['rows']['crdb_agent_skills']['verdict'])"
               →  DESIGNED                                              (observed 2026-08-16)
               python skills/validate-spec.py skills/ --strict
               →  3 skill(s), 0 error(s), 0 warning(s)                  (observed 2026-08-16)
               python skills/designing-diachronic-gates/scripts/assert_gate_refuses.py --parser-self-test
               →  parser self-test: OK  (its last three lines assert that an ADMISSION is a FAIL)
say this:      "We authored two CockroachDB Agent Skills and published them under Apache-2.0
               through both the Agent Skills spec and a Claude Code plugin marketplace. Each
               ships a script that fails when the guarantee does not hold, and the lane runs the
               failing half first: nine unwelding rows against a throwaway CockroachDB node,
               four of which must ADMIT, plus nine planted violations each refused by name.
               And we file it DESIGNED, not exercised, because no run of either script is
               captured under evidence/ — it is a fourth tool past a floor of two, and it is not
               promoted to lengthen a list."
never say:     "All four contest tools are exercised." Three are. This one is DESIGNED, and the
               `k3` card says so in the same capitals it says EXERCISED in.
               "Our skill was merged upstream." Nothing is merged; the claims-grep fails the
               build on that sentence. "We contributed a skill to CockroachDB." It is staged and
               ready to file. "The skills lane is green at HEAD." The recorded green is at an
               older commit, which `docs/CI-STATE.md` itself calls five commits behind.
source:        census/crdb-four-tools.md §4
```

**Why the promotion was withdrawn rather than argued.** The case for it was real — the generator's
own definition of EXERCISED is *"it ran, and a committed artefact **or a check in this repository**
records the result"*, and `.github/workflows/skills.yml` is such a check. But the recorded green is
at commit `2dc5c86`, which `docs/CI-STATE.md` itself calls five commits behind the tip it was
measuring, and **the cure for that is a dispatch, not a sentence in a census.** A row promoted on
an argument, on the one page a judge is pointed at for states, would be the single worst kind of
error this document can make — and the fix costs nothing, because the floor is two and three are
exercised. **Capturing a run to promote this row is explicitly out of scope for this wave**; the
state is reported here, not created.

---

### 2.5 AWS in the live request path (LIVE)

Five AWS services run on the path of a single unauthenticated request, and four of the five are
entailed by one anonymous 200 on `/v1/health`.

#### AW1 · AWS Lambda

```
state:         LIVE
what it is:    the compute. One Python 3.13 function is the entire server — router, API, static
               console and refusal logic — invoked per HTTP request. There is no web framework
               and no adapter: `app.handler(event, context)` is the server.
where:         infra/modules/demo-api/main.tf:326-421 · app.py:522 def handler(...)
verify in 60s: curl -si $ORIGIN/v1/health | head -1     →  HTTP/1.1 200 OK
               (and `x-amzn-RequestId` in the headers is the Lambda invocation id)
say this:      "The whole demo API is one Python 3.13 Lambda function in ap-southeast-1. A
               Lambda invocation is already a function call with a dict argument, so there is no
               framework between the request and the handler."
never say:     "It runs on ECS / Fargate / EC2 / API Gateway." There is no container service and
               no API Gateway in this stack.
source:        census/aws-live-path.md §2.1
```

Worth one clause in any longer telling: three `lifecycle.precondition` blocks refuse at **plan**
time a configuration that would deploy cleanly and fail later — including one that refuses
`demo_signer_sub == demo_countersigner_sub` **because the database refuses it**, which is the AWS
half of this project deferring to the CockroachDB half.

#### AW2 · AWS Lambda Function URL

```
state:         LIVE
what it is:    the hostname. A Lambda-native HTTPS endpoint with `authorization_type = NONE`,
               which is what makes the demo free to access as the rules require. HTTPS is
               terminated by AWS on its own managed certificate.
where:         infra/modules/demo-api/main.tf:425-453 · variables.tf:49 (default "NONE")
verify in 60s: curl -s -o /dev/null -w '%{http_code}\n' $ORIGIN/v1/health   →  200
               with NO credential, NO signature and NO header — that IS the proof of NONE
say this:      "The demo is a Lambda Function URL with authorization_type NONE. An anonymous
               curl with no signature gets a 200, which is exactly what the rules' freely-
               accessible requirement asks a judge to be able to do."
never say:     "CloudFront serves the demo" (see DC1). "We provisioned an ACM certificate" (the
               wildcard subject shows it is AWS's). And do not append "…and it runs as a narrow
               SQL role": the repository DECLARES the narrow role and a LOCAL probe exercises
               it, which is a repository fact and not a fact about the deployed connection.
source:        census/aws-live-path.md §2.2
```

The missing `cors` block is a decision, not an omission: under decision D1 the console and the API
answer on one origin, so every console request is same-origin and `allow_origins = ["*"]` would
change nothing about whether the demo works and exactly one thing about what an attacker can read.

#### AW3 · AWS IAM — the Lambda execution role

```
state:         LIVE
what it is:    the identity every request runs as. Lambda injects the role's temporary
               credentials into the handler's environment and `db.py` signs with them. The role
               can do two things: write its own log group, and read ONE named SSM parameter.
where:         infra/modules/demo-api/main.tf:247-274, :276-322 (aws_iam_role_policy.dsn_access)
               verticals/mainline/apps/demo-api/src/mainline_demo_api/db.py:223-232
verify in 60s: sed -n '276,322p' infra/modules/demo-api/main.tf
               →  first line `data "aws_iam_policy_document" "dsn_access" {`
say this:      "The Lambda's execution role can do two things: write its own log group, and read
               one named SSM parameter. ssm:GetParameter on one ARN — not a prefix, not a
               wildcard — and kms:Decrypt conditioned on kms:ViaService and on the encryption
               context naming that same parameter."
never say:     "least privilege" as a slogan with nothing behind it. Say the two actions and the
               one ARN; that is the checkable version and it is stronger.
source:        census/aws-live-path.md §2.3
```

AWS STS is on this path and is folded in here rather than given a row: `db.py:225` reads
`AWS_SESSION_TOKEN` and adds it as a signed header, which is assume-role output being consumed on
every cold start. A separate "AWS STS" line in a close block would be logo-padding, and R5 says a
row that adds a logo outranks nothing.

#### AW4 · AWS Systems Manager Parameter Store

```
state:         LIVE
what it is:    where the CockroachDB Cloud DSN lives. One parameter, fetched once per execution
               environment by name, with WithDecryption sent, over a request the handler signs
               itself.
where:         db.py:214-305 `_ssm_get_parameter` · :205-211 the SigV4 key derivation
               infra/modules/demo-api/main.tf:135-137 MAINLINE_DSN_PARAM
verify in 60s: .venv/Scripts/python.exe -m pytest verticals/mainline/apps/demo-api/tests/
               test_envelope.py -q -k "ssm or aws_sdk"     →  2 passed, 56 deselected
say this:      "The Lambda reads its database credential from SSM Parameter Store, once per
               execution environment, over an HTTPS request it signs with SigV4 built from
               hashlib and hmac."
never say:     "The DSN is in Terraform state" or "in an environment variable" — Terraform
               constructs the ARN and never reads the value, and the module's variable
               validation REJECTS an attempt to pass the DSN. And do not add the adjective
               "SecureString" until somebody with a credential reads the applied type back
               (escalation E-1, §7). "Reads its credential from SSM Parameter Store" needs no
               adjective and is fully proven by the 200.
source:        census/aws-live-path.md §2.4
```

**Why the 200 proves SSM ran.** `health()` returns 503 `dsn_unset` when the DSN cannot be
resolved; in the deployed stack the environment variable route is impossible, because the module's
`extra_environment` deny-list's first entry is `MAINLINE_DSN`. So a 200 entails the signed
`ssm:GetParameter` succeeded. **And it has been falsified once**, which is what makes it credible:
on 2026-08-14 the stack was applied before the parameter was written and the same origin returned
`ok=false, reason="dsn_unset"` with the verbatim SSM error `{"__type":"ParameterNotFound"}` —
recorded in `evidence/deploy/APPLIED.md` and reproduced 20 times in `evidence/deploy/judge-walk.json`.

#### AW5 · Amazon CloudWatch Logs

```
state:         LIVE  (declaration + invocation id; reading an event needs the account)
what it is:    one Terraform-managed log group named as the function's log destination, JSON
               format, level set, retention 7 days — plus a per-invocation LOG BYTE BUDGET in
               the handler, because a log group has retention and not a quota and ingestion is
               the charged term.
where:         infra/modules/demo-api/main.tf:239-243, :373-378 logging_config, :382-386 depends_on
               verticals/mainline/apps/demo-api/src/mainline_demo_api/logbudget.py
verify in 60s: curl -sD- -o /dev/null $ORIGIN/v1/health | grep -i 'x-amzn-requestid'
               →  x-amzn-RequestId: <a uuid> — the key the invocation is recorded under
say this:      "Every invocation is logged to a Terraform-managed CloudWatch log group in JSON
               format, and the handler enforces a per-invocation log byte budget on top, because
               a log group has retention and not a quota."
never say:     "Here are the logs" to an anonymous reader. What a stranger can check is the
               request-id header and the declaration — plus eleven distinct AWS-issued
               invocation ids already committed in evidence/demo/live-beats.json.
source:        census/aws-live-path.md §2.5
```

#### AW6 · Hand-rolled SigV4 with no AWS SDK in the package (technique, not a service)

```
state:         LIVE
what it is:    the deployment package's entire third-party dependency closure is `psycopg`.
               There is no AWS SDK in it, and the one AWS call it makes is signed by hand from
               hashlib and hmac — deliberately, so the package's behaviour does not depend on
               which boto3 AWS ships.
where:         verticals/mainline/apps/demo-api/pyproject.toml:47-50 · db.py:26 (the comment
               where the import would have been) · retry.py:12
verify in 60s: grep -rn "boto3" verticals/mainline/apps/demo-api/src/mainline_demo_api/*.py
               →  3 hits, all comments
               pytest …test_envelope.py::test_no_web_framework_or_aws_sdk_is_imported → 1 passed
say this:      "The Lambda package pins two wheels and nothing else. The AWS call it makes is
               SigV4-signed by hand — no boto3, no botocore — and a test enforces it rather than
               a comment asking politely."
never say:     that this is a general SDK replacement. It signs exactly one operation,
               `AmazonSSM.GetParameter`, and only that one.
source:        census/aws-live-path.md §3
```

---

### 2.6 AWS applied as infrastructure (APPLIED)

**One apply, 2026-08-14: `24 created, 0 changed, 0 destroyed`, 37 resources in state** —
`evidence/deploy/APPLIED.md:14-15`, with the 24 addresses enumerated in
`evidence/deploy/cost/plan-shape.json`. **APPLIED is not exercised-in-anger, and every row below
says so in its own words:** no program in this repository has read these resources back out of
CloudWatch, SNS or Budgets. The evidence is the apply transcript plus the plan that names exactly
those addresses. That is a strong chain and it is not a readback.

#### AP1 · Amazon SNS — the stop topic

```
state:         APPLIED
what it is:    one topic, one policy that replaces SNS's default entirely, one Lambda
               subscription. Everything that publishes to it means the same thing — stop the
               demo — so the responder need not know which alarm spoke.
where:         infra/modules/cost-guard/main.tf:198 (topic) · :322 (policy) · :541 (subscription)
verify in 60s: grep -n 'resource "aws_sns_topic' infra/modules/cost-guard/main.tf
               →  198:resource "aws_sns_topic" "guard" {
say this:      "An SNS topic is applied in the account. It is a stop topic, not a notification
               topic: its one confirmed subscriber is a Lambda that reserves zero concurrency on
               the demo function, and its policy names the three alarms allowed to publish
               rather than using a wildcard."
never say:     "SNS alerts us." Nobody is subscribed by email — the module's comment explains
               that an unconfirmed email subscription is a control that looks present and is
               not. And never say the topic has carried a message; no artefact records a publish.
source:        census/aws-repo-and-infra.md A1
```

#### AP2 · AWS Budgets

```
state:         APPLIED
what it is:    one COST budget, USD 25.00 monthly, ACTUAL rather than FORECASTED, GREATER_THAN
               100 %, scoped by a Service cost filter, with credits and refunds excluded from
               the evaluated cost, publishing to the same stop topic.
where:         infra/modules/cost-guard/main.tf:553-637
verify in 60s: grep -n 'resource "aws_budgets_budget"' infra/modules/cost-guard/main.tf  →  1 hit
say this:      "A USD 25/month AWS Budget is applied, and it is wired to the stop rather than to
               an inbox. It evaluates ACTUAL cost with promotional credit excluded, because a
               flood paid for by credits is still a flood."
never say:     "The budget caps our spend." It caps nothing: Budgets evaluates against Cost
               Explorer on a lag AWS documents and no setting shortens. It is the backstop; the
               two invocation alarms are the bound. And never say it has fired.
source:        census/aws-repo-and-infra.md A2
```

#### AP3 · Amazon CloudWatch — seven metric alarms

```
state:         APPLIED
what it is:    7 alarms on 4 metrics across 3 timescales. The five whose metrics have a physical
               ceiling each carry a plan-time precondition proving the threshold is reachable.
where:         infra/modules/demo-api/main.tf and infra/modules/cost-guard/main.tf
               names cross-checked against the plan in evidence/deploy/verify/post-apply-dry.json
verify in 60s: python -c "import json;print(len(json.load(open('evidence/deploy/cost/
               plan-shape.json',encoding='utf-8'))['alarms']))"   →  7
say this:      "Seven CloudWatch alarms are applied across four metrics and three timescales,
               and the five whose metrics have a physical ceiling each carry a plan-time
               precondition proving the threshold is reachable — an alarm whose threshold sits
               above what the metric can reach is a control that looks present and is not, and
               Terraform refuses to plan one here."
never say:     "our alarms caught X", or anything implying an alarm has fired. No artefact
               records any of the seven transitioning to ALARM, and none has been read back.
source:        census/aws-repo-and-infra.md A3
```

#### AP4 · Amazon CloudWatch — one dashboard

```
state:         APPLIED
what it is:    one dashboard, five widgets, whose header widget names the thing most dashboards
               hide: the Function URL is unauthenticated, and what bounds it is the account's
               measured concurrency ceiling of 10.
where:         infra/modules/demo-api/main.tf:841-978
verify in 60s: sed -n '841,978p' infra/modules/demo-api/main.tf | grep -cE '^\s+type\s+='  →  5
say this:      "A CloudWatch dashboard is applied, and its header widget names the thing most
               dashboards hide: what bounds an unauthenticated URL here is the account's
               measured concurrency ceiling, not a control we chose."
never say:     "the dashboard shows our live traffic." No artefact records it being read.
source:        census/aws-repo-and-infra.md A4
```

#### AP5 · AWS Lambda — the cost-guard responder (the second function)

```
state:         APPLIED
what it is:    a second Lambda whose only job is to stop the first one. It refuses every SNS
               record whose TopicArn is not the one topic it was given, and it holds -1 reserved
               concurrency because this account's quota of 10 makes every positive reservation
               un-appliable.
where:         infra/modules/cost-guard/main.tf:469
verify in 60s: grep -rn 'resource "aws_lambda_function"' infra --include=*.tf   →  2 hits
say this:      "A second Lambda is applied whose only job is to stop the first one."
never say:     "The kill switch has been tested end to end in the account." Its refusal behaviour
               is unit-tested offline; no artefact records a real breach, a real publish, or a
               real PutFunctionConcurrency call. The path is applied and unexercised.
source:        census/aws-repo-and-infra.md A5
```

#### AP6 · AWS IAM — a one-action grant with an explicit self-Deny

```
state:         APPLIED
what it is:    the responder's role carries an explicit Deny on DeleteFunctionConcurrency, so
               even a responder rewritten to restore itself cannot.
where:         infra/modules/cost-guard/main.tf, aws_iam_role_policy.responder_stop
verify in 60s: grep -n 'DeleteFunctionConcurrency' infra/modules/cost-guard/main.tf
say this:      "The stop is enforced by IAM rather than by good behaviour: the responder's role
               carries an explicit Deny on DeleteFunctionConcurrency. A stop that can be undone
               by the thing being stopped is not a stop."
never say:     "least privilege everywhere." The role also carries AWS's managed basic-execution
               policy, which is wildcarded over log groups; the module names that and declines
               to narrow it.
source:        census/aws-repo-and-infra.md A6
```

#### AP7 · Amazon CloudWatch Logs — the responder's log group

```
state:         APPLIED
what it is:    the second log group, created by Terraform with a finite retention.
where:         infra/modules/cost-guard/main.tf, aws_cloudwatch_log_group.responder
verify in 60s: grep -n 'aws_cloudwatch_log_group' infra/modules/cost-guard/main.tf   →  1 hit
say this:      "Both log groups in this stack are created by Terraform with a finite retention,
               so neither is an orphan a Lambda made and nobody owns."
never say:     anything about log *content* — that is AW5's row and it needs the account.
source:        census/aws-repo-and-infra.md A7
```

#### AP8 · Amazon S3 — the Terraform state bucket, with native S3 locking

```
state:         APPLIED
what it is:    a versioned, private, encrypted state bucket created by
               scripts/deploy/bootstrap_state.sh with the AWS CLI (it cannot be created by the
               run that needs it to exist), locked by S3 itself rather than by a lock table.
where:         infra/envs/demo/backend.tf:30 · evidence/deploy/APPLIED.md:23-25
verify in 60s: grep -n 'use_lockfile' infra/envs/demo/backend.tf
say this:      "State lives in a versioned, private, encrypted S3 bucket locked by S3 itself —
               one fewer resource, one fewer bill line, and one fewer thing to remember to
               delete."
never say:     that this is the evidence store. It carries no Object Lock configuration and
               holds no checkpoint; the evidence store is DC3 and has never been created.
source:        census/aws-repo-and-infra.md A8
```

---

### 2.7 AWS exercised in the repository, outside the request path (REPO)

**The sharpest check on ruling R4: the Bedrock work is not even in the demo's region.** The live
demo is `ap-southeast-1` (Singapore); every Bedrock artefact in this census is `ap-southeast-2`
(Sydney), and all 24 JSON artefacts under `evidence/aws/` carry that region.

#### RP1 · Amazon Bedrock — Claude inference through `au.*` inference profiles

```
state:         REPO
what it is:    seven live Claude legs in Sydney, each with an AWS request id, each recorded as a
               cassette that replays to a byte-identical decision and refuses to load if
               tampered with.
where:         packages/trappoint-recall/src/trappoint_recall/eval/bedrock_backend.py
               evidence/aws/agent/live-run.json · evidence/deploy/aws-live.json
verify in 60s: python scripts/aws/agent_live.py --verify
               →  7 cassette lines all ok; `replay hashes equal: True`; `verdict: PASS`
say this:      "Amazon Bedrock is real in this repository: seven live Claude legs in Sydney, each
               with an AWS request id, each recorded as a cassette that replays to a
               byte-identical decision. It is not in the demo's request path — the demo's Lambda
               imports psycopg and nothing else, deliberately."
never say:     "The demo runs on Bedrock." The live URL makes no model call. And never quote the
               live legs as running on the shipping model: they ran on an older Claude
               generation while the request builders target the pinned one.
source:        census/aws-repo-and-infra.md R1
```

#### RP2 · Amazon Bedrock — embeddings (Titan Text v2)

```
state:         REPO
what it is:    2,060 real 1,024-dimension vectors produced in Sydney and loaded into CockroachDB
               VECTOR(1024) columns, searched through a C-SPANN index with both prefix columns
               bound. When a second embedding model turned out not to be servable in-region
               without cross-region routing, the refusal and the request id were published
               rather than the global profile being used.
where:         evidence/aws/embeddings/ · evidence/aws/ann/ann-proof.json
verify in 60s: python scripts/aws/verify_evidence.py
               →  "1235 assertions across 40 of 40 declared invariants. PASS"
say this:      "Titan Text Embeddings v2 produced 2,060 real 1,024-dimension vectors in Sydney;
               they sit in CockroachDB VECTOR(1024) columns and are searched through a C-SPANN
               index with both prefix columns bound."
never say:     the phrase MUST-NOT-CLAIM family 1 bans. Inference is in Sydney and the database
               is in Singapore, because the closer region is Advanced-tier only on CockroachDB
               Cloud; there is no end-to-end residency and the honesty card says so.
source:        census/aws-repo-and-infra.md R2
```

#### RP3 · Amazon CloudWatch — the read-only `AWS/Bedrock` metric census

```
state:         REPO
what it is:    110 read-only GetMetricStatistics calls against the AWS/Bedrock namespace,
               reconciled against this repository's own token ledgers, with every disagreement
               named. The total AWS bill for the whole fleet is taken from AWS's numbers rather
               than ours.
where:         evidence/aws/cloudwatch/bedrock-metrics.json · reconciliation.json
verify in 60s: python -c "import json;print(json.load(open('evidence/aws/cloudwatch/
               bedrock-metrics.json',encoding='utf-8'))['payload']['api_call_summary'])"
say this:      "We reconciled our own token accounting against AWS's counters and published every
               place they disagree — the fleet total is taken from AWS's numbers rather than
               ours, because when two sources disagree about what you spent the honest one is
               the one that is not you."
never say:     that this reader provisioned or invoked anything. Its allow-list is enforced
               before the request is signed, and the artefact records the complete call log.
               This is also the row whose generator entry is mistitled — see over-claim O1, §5.
source:        census/aws-repo-and-infra.md R3
```

#### RP4 · AWS Service Quotas and Lambda account settings

```
state:         REPO
what it is:    the account's concurrency ceiling — 10 — read from two different AWS APIs in two
               regions, and the number every alarm threshold divides by.
where:         evidence/deploy/cost/alarm-reachability.json
verify in 60s: python -c "import json;print(json.load(open('evidence/deploy/cost/
               alarm-reachability.json',encoding='utf-8'))['account_facts_measured'])"  →  10.0
say this:      "The cost bound is arithmetic over a measured account quota, not a guess: the
               ceiling is 10, we read it from two AWS APIs in two regions, and Terraform refuses
               at plan time to create any alarm whose threshold sits above what that makes
               physically reachable."
never say:     "we capped concurrency." AWS refuses every positive reservation on an account
               whose ceiling is 10, so -1 is the only value that applies.
source:        census/aws-repo-and-infra.md R4
```

#### RP5 · Policy-as-code over the Terraform plan (the gate that actually runs)

```
state:         REPO for the gate that runs; the Rego is DECLARED and has never been executed
what it is:    a 15-rule custody gate over the Terraform plan, with a self-test that plants a
               broken plan for each rule and requires a refusal.
where:         scripts/custody/check_evidence_plan.py · infra/policy/custody/*.rego (596 lines,
               never run — the file's own header says so at line 22)
verify in 60s: python scripts/custody/check_evidence_plan.py
               →  PASS OL-1 … "selftest OK — 15 rules"
say this:      "The custody controls on S3 Object Lock and the KMS signing key are enforced as
               policy over the Terraform plan, and the gate has been observed refusing a broken
               plan for each of its fifteen rules. A check that has never been red asserts
               nothing."
never say:     "OPA/conftest enforces this." The Rego has never been executed; `opa` is not
               installed on the machine it was written on, and it is a specification rather than
               a control until it runs.
source:        census/aws-repo-and-infra.md R5
```

#### RP6 · AWS Cost Explorer and pre-existing AWS Budgets, read-only

```
state:         REPO
what it is:    a real `aws ce get-cost-and-usage` call plus a reading of the account's three
               pre-existing budgets — all three permanently breached, none attached to any
               action, which is why the guard exists.
where:         evidence/aws/aws-quota-and-cost.json  (account id masked; no credential in it)
verify in 60s: python -c "import json;print(json.load(open('evidence/aws/aws-quota-and-cost.json',
               encoding='utf-8'))['part_2b_the_budget']['budget_actions_across_all_three'])" → 0
say this:      "Before we wrote a budget we read the account's existing ones. There were three,
               all permanently breached, none attached to a single action. Ours is scoped to
               three services, evaluates ACTUAL cost with credit excluded, and publishes to a
               topic whose only subscriber turns the demo off."
never say:     that we monitor spend continuously, or that any figure is live. It is a reading
               taken on 2026-08-12 and it has not been retaken.
source:        census/aws-repo-and-infra.md R6
```

---

### 2.8 AWS written and never created (DECLARED)

#### DC1 · Amazon CloudFront + Origin Access Control — ruling R3, the most dangerous row here

```
state:         DECLARED
what it is:    a distribution and two Origin Access Controls, written and Terraform-valid; the
               plan builds them (35 resources with the flag on against 24 with it off). AWS
               holds new CloudFront resources on this account pending verification.
where:         infra/envs/demo/main.tf:38-52 — the real terraform apply transcript of 2026-08-10
verify in 60s: sed -n '38,52p' infra/envs/demo/main.tf   →  the verbatim AWS refusal,
               "AccessDenied: Your account must be verified before you can add new CloudFront
               resources", reproduced from a bare CLI call under AdministratorAccess
say this:      "The CloudFront distribution and both Origin Access Controls are written and
               Terraform-valid. AWS holds new CloudFront resources on this account pending
               verification — a 403 we reproduced from a bare CLI call — so decision D1 gave the
               hostname to the Lambda Function URL, and nothing in this stack can hold the demo
               URL hostage."
never say:     "CloudFront serves the demo." "Behind CloudFront." "CDN-fronted." "At the edge."
               The grant that would let a distribution invoke the function is `count = 0`, and
               the module says `count = 0` rather than "created but harmless" on purpose.
source:        census/aws-repo-and-infra.md D1 · census/aws-live-path.md §4.2
```

#### DC2 · Amazon S3 — the private demo-site bucket

```
state:         DECLARED
what it is:    the private-origin bucket the unrealised distribution would have signed requests
               to. It has never held an object.
where:         infra/modules/demo-site/
verify in 60s: GET / on the live origin → `x-mainline-static: index.html`, i.e. bytes from the
               deployment zip, not from a bucket
say this:      "The static console has a private-origin S3 design that is written and planned and
               was never applied, because the distribution that would have signed requests to it
               cannot be created on this account. The console is served from the Lambda package."
never say:     "We host the console on S3."
source:        census/aws-repo-and-infra.md D2
```

#### DC3 · Amazon S3 + Object Lock (COMPLIANCE) — the evidence store

```
state:         DECLARED
what it is:    a COMPLIANCE-mode Object Lock bucket in a separate account, written with
               prevent_destroy on every resource, its rules enforced by RP5's gate before
               anything is applied. It has not been created.
where:         infra/envs/evidence/ — never applied at all
verify in 60s: python -c "import json;d=json.load(open('qa/test-state.json',encoding='utf-8'));
               print(d['external_checks']['custody_bundle_verification'])"
               →  passed 9, failed 0, not_checked 7, total 16, exit_code 2
say this:      "The evidence store is specified as a COMPLIANCE-mode Object Lock bucket in a
               separate account and it has not been created. Offline bundle verification exits
               2 — everything that ran held, and seven checks did not run."
never say:     "Our evidence is under Object Lock", and never the sentence MUST-NOT-CLAIM
               family 8 bans about the custody bundle. What is checked is the Merkle structure,
               not the signatures over it.
source:        census/aws-repo-and-infra.md D3
```

#### DC4 · AWS KMS — an `ECC_NIST_P256` `SIGN_VERIFY` key

```
state:         DECLARED
what it is:    the checkpoint signing key, specified as an asymmetric P-256 key whose
               destruction is denied outside a break-glass role, with four rules in RP5's gate
               enforcing that specification before an apply. No key exists.
where:         infra/envs/evidence/ · infra/policy/custody/kms_custody.rego
verify in 60s: grep -rn 'aws_kms_key' infra --include=*.tf   →  one declaration, in the
               never-applied evidence root
say this:      "The checkpoint signing key is specified as an asymmetric P-256 KMS key whose
               destruction is denied outside a break-glass role, and four rules in a gate that
               has been observed refusing each of them enforce that specification before an apply."
never say:     "Checkpoints are signed by KMS." No key exists; the signer is implemented against
               an injected client and unit-tested offline.
source:        census/aws-repo-and-infra.md D4
```

#### DC5 · AWS CloudTrail — custody of the custodian

```
state:         DECLARED
what it is:    a trail specified into a third account with log-file validation on, so that AWS
               produces an independent signed digest chain over the same events — deliberately
               one we could not forge. One resource, one root module, zero applies.
where:         infra/envs/evidence/
verify in 60s: grep -rn 'aws_cloudtrail' infra --include=*.tf   →  one declaration
say this:      "CloudTrail is specified into a third account with log-file validation on, so that
               AWS produces an independent signed digest chain over the same events. It is
               written and has not been applied; no trail exists in the account."
never say:     "CloudTrail records our custody events." Nothing is recorded.
source:        census/aws-repo-and-infra.md D5
```

#### DC6 · Amazon EventBridge — corrected downward, and recommended out of the close block

```
state:         DECLARED, and weakly — there is no EventBridge resource in the tree at all
what it is:    scheduled patrol runs are designed for EventBridge and currently run from a
               container entrypoint.
where:         nowhere in infra/
verify in 60s: grep -rn "aws_cloudwatch_event\|aws_scheduler" infra --include=*.tf
               →  no output  (exit 1 — the absence is the finding)
say this:      if it is said at all — "scheduled patrol runs are designed for EventBridge and
               currently run from a container entrypoint. There is no EventBridge resource in
               the tree."
never say:     "We use EventBridge." **Recommendation carried into the close block: drop this
               row.** It is the one line in the AWS list a judge could falsify with a single
               grep, and the list is strong enough without it.
source:        census/aws-repo-and-infra.md D6
```

---

### 2.9 Checked, absent, and kept (NOT-AVAILABLE)

A checked-and-absent row is a credibility asset: a services list that omits what you checked and
could not have is a list a judge cannot audit.

#### NA1 · Amazon Bedrock Rerank

```
state:         NOT-AVAILABLE
what it is:    listwise reranking is not offered in our region; we published the control-plane
               listing that shows it and took no dependency.
where:         evidence/aws/ (the control-plane listing)
verify in 60s: python -c "import json;print(json.load(open('evidence/tool-usage/
               aws-services.json',encoding='utf-8'))['rows']['aws_bedrock_rerank']['verdict'])"
               →  NOT-AVAILABLE
say this:      "Bedrock Rerank is not offered in our region. We checked, we published the
               listing that shows it, and we took no dependency on it — listwise reranking runs
               on the Claude profile instead, and CockroachDB's own
               vector_search_rerank_multiplier governs the ANN side."
never say:     that we *chose* not to use it after evaluating it. We could not have used it.
source:        census/aws-repo-and-infra.md N1
```

#### NA2 · AWS X-Ray — the header is present, active tracing is not

```
state:         NOT-AVAILABLE
what it is:    `X-Amzn-Trace-Id` appears on every response with `Sampled=0`. That header is
               injected by the Lambda service, not by us, and there is no tracing configuration
               anywhere in infra/.
where:         nowhere in infra/
verify in 60s: grep -rn "tracing_config\|xray\|AWSXRay" infra/modules/demo-api/main.tf
               infra/envs/demo/main.tf   →  no output
say this:      nothing, ordinarily. If asked: "the trace header on our responses is the Lambda
               service's; we did not enable active tracing."
never say:     "distributed tracing with X-Ray." Recorded here specifically because that header
               is exactly the sort of thing that produces an accidental over-claim.
source:        census/aws-live-path.md §4.5 · census/aws-repo-and-infra.md §1
```

#### NA3 · CockroachDB multi-region · NA4 · `crdb_internal` schema

Both are rows above — TX11 and TX6 — and are repeated here only so the negative states can be
counted in one place. Two of the CockroachDB rows are deliberate, measured absences.

---

## 3. TOTALS, AND THE ROWS THAT MUST NOT BE DOUBLE-COUNTED

| domain | LIVE | REPO | APPLIED | DECLARED | NOT-AVAILABLE | rows |
|---|---|---|---|---|---|---|
| CockroachDB — programmable | 10 | 2 | — | — | — | 12 |
| CockroachDB — schema & index | 4 | 8* | — | — | — | 12 |
| CockroachDB — transactional | 4 | 4 | — | 1 | 2 | 11* |
| CockroachDB — the four named tools | — | 3 | — | 1† | — | 4 |
| AWS — live request path | 6 | — | — | — | — | 6 |
| AWS — applied | — | — | 8 | — | — | 8 |
| AWS — repository | — | 6 | — | — | — | 6 |
| AWS — declared | — | — | — | 6 | — | 6 |
| AWS — checked and absent | — | — | — | — | 2 | 2 |
| **total** | **24** | **23** | **8** | **8** | **4** | **67** |

† **CT4, Agent Skills, is the one tool row that is not REPO**, and it is counted in the DECLARED
column because DECLARED is this page's bucket for the generator's `DESIGNED` (§0). The bucket is
slightly harsher than the row: the scripts *do* run locally, which is why CT4's own words are
**shipped and not evidenced** rather than *never run*. The count is deliberately taken at the
harsher reading — **3 of the 4 contest tools carry a committed transcript, against a floor of
two.**

\* **Three rows carry two states each and are counted once, under the state that governs the
sentence a close block would say.** SC10 is REPO for the foreign key and LIVE for the rows it
references; TX3 is REPO for the isolation downgrade that was exercised today and DECLARED for the
case that cannot build its world; TX6 is NOT-AVAILABLE for the restricted schema and LIVE for the
unqualified builtin. The split *is* the point of those three rows, and flattening it would be
exactly the over-claim they exist to prevent — so the count is conservative and the row text is
not. Every column sums, and 24 + 23 + 8 + 8 + 4 = 67.

**Four pairs are two halves of one fact and must never be counted twice, or told twice:**

| pair | who owns which half |
|---|---|
| SC2 + PL5 | SC2 is the generated column that **computes** the digest; PL5 is the trigger that **verifies the predecessor**. "The database computes and checks its own hash chain" is one sentence built from two rows. |
| CT2 + SC3 | CT2 owns the 3 `cspann` indexes and the prefix rule; SC3 owns the generated `tsvector`. Together they are the R8 hybrid claim: 4 VECTOR columns, 3 indexes, 1 tsvector, 5 inverted indexes. |
| AW5 + AP3/AP4/AP7 | AW5 is CloudWatch **on the request path** (log group + invocation id). AP3, AP4 and AP7 are CloudWatch **as applied infrastructure**. The generator has one `aws_cloudwatch` row for what is really three different claims — over-claim O1. |
| TX1 + TX8 | one transaction across four beats is only possible because each refusable beat has its own savepoint. Say the savepoint when you say the single transaction. |

---

## 4. THE UNDER-CLAIM LIST — what this census asserts that the generator does not yet emit

Ruling **R6**: every proposed row arrives as prose **plus an exact detector**, so a follow-up can
add it to `scripts/submission/capture_tool_evidence.py`. **This worker did not edit that script,
did not weaken a ratchet, and did not touch `HONESTY.md`, `CI-STATE.md` or `MUST-NOT-CLAIM.md`.**

`evidence/tool-usage/crdb-features.json` holds 14 rows and `aws-services.json` holds 12. Between
them they carry **no row at all** for enums, generated columns, full-text search, partial indexes,
composite foreign keys, PL/pgSQL, recursive CTEs, `RETURNING`, savepoints, the retry code, the HLC
builtin, the Lambda Function URL, SNS, Budgets, the alarms, the dashboard, the second Lambda, the
state bucket, Service Quotas or Cost Explorer. The census is under-claiming, and here is the fix.

### 4.1 CockroachDB — proposed rows (24)

| # | proposed key | state | detector (exact) |
|---|---|---|---|
| U-C1 | `crdb_plpgsql_functions` | LIVE | SQL: `pg_proc ⋈ pg_language WHERE lanname='plpgsql' AND prokind='f'` → expect **26** |
| U-C2 | `crdb_plpgsql_procedures` | LIVE | same with `prokind='p'` → expect **2** |
| U-C3 | `crdb_triggers` | LIVE | SQL: `count(*) FROM pg_trigger WHERE NOT tgisinternal` → **39**; `count(*) FROM information_schema.triggers` → **59**. Record **both** — recording one is how "59 triggers" became quotable |
| U-C4 | `crdb_agent_skills` — **detector only; the verdict stays DESIGNED** | **DESIGNED** | two-part predicate, proposed so the row's *basis* becomes machine-checkable, **not** so the verdict moves. Part 1: `.github/workflows/skills.yml` contains `assert_gate_refuses.py`, `assert_prefix_index_used.py`, `--self-test --docker-only` and `must exit 1`. Part 2: the recorded green's **commit** is stored beside the run id, so a stale green can never masquerade as green at HEAD. **Promotion is refused on Part 2's own evidence:** the recorded green is at `2dc5c86`, five commits behind. The verdict moves when a run is captured under `evidence/`, and this wave does not capture one |
| U-C5 | `crdb_append_only_weld` | LIVE | SQL: `count(DISTINCT tgrelid) FROM pg_trigger t JOIN pg_proc p ON p.oid=t.tgfoid WHERE NOT tgisinternal AND p.proname='fn_refuse_mutation'` → **17** |
| U-C6 | `crdb_rls_force` | LIVE | SQL: `count(*) FROM pg_class WHERE relforcerowsecurity` **equals** `… WHERE relrowsecurity` → 4 = 4 |
| U-C7 | `crdb_rls_policies` | LIVE | SQL: `count(*) FROM pg_policies` → **25**; `WHERE permissive='restrictive'` → **5** |
| U-C8 | `crdb_rls_deliberate_exclusion` | LIVE | SQL: `obj_description('mainline_ops.outbox'::regclass) LIKE 'NO ROW LEVEL SECURITY%'` |
| U-C9 | `crdb_role_lattice` | LIVE | SQL: the nine `rolname` values; assert `rolcanlogin = false` on all nine |
| U-C10 | `crdb_privilege_floor` | LIVE | SQL: public table-privileges in the 5 app schemas = **0**; `DELETE` grants in `mainline`/`mainline_meas` = **0** |
| U-C11 | `crdb_no_security_definer` | LIVE | SQL: `count(*) FROM pg_proc WHERE prosecdef AND lanname='plpgsql'` → **0** |
| U-C12 | `crdb_recursive_cte` | REPO | grep `^WITH RECURSIVE` **anchored** over `verticals/mainline/db/queries` and `verticals/mainline/packages` → **4** sites (anchoring excludes the 5 prose mentions and the commented one in `0034`) |
| U-C13 | `crdb_returning_cas` | LIVE | grep `RETURNING` over `verticals/mainline/apps/demo-api/src` → `transitions.py:838`; `RETURNING .* INTO` over `db/migrations/0117`, `0118` → 2 sites |
| U-C14 | `crdb_rendered_object_per_file` | LIVE | filesystem, no cluster: `ls db/migrations \| grep -c _fn_` = 26, `_proc_` = 2, `_trg_` = 39, `_policy_` = 25 — **each must equal its catalog count**, which is what makes it a drift detector rather than a count |
| U-C15 | `crdb_live_procedure_call` | LIVE | HTTP, no credential: `POST /v1/demo/gate-run` → `data.beats[1].statement` **startswith** `CALL mainline.merge_permit(` and `data.beats[2].sqlstate == "P0001"` and `data.verdict == "PROVEN"`. **Corrected here:** W6 proposed `statement_refs[]`; the live response carries `statement` on each beat and has no `statement_refs` key at all — measured today (§8, call 2) |
| U-C16 | `crdb_enums` | LIVE | SQL: `count(*) FROM pg_type t JOIN pg_enum e ON e.enumtypid=t.oid` → **36** labels over **7** types |
| U-C17 | `crdb_generated_stored` | LIVE | SQL: `count(*) FROM information_schema.columns WHERE is_generated='ALWAYS'` → **8**; assert the two `chain_digest` expressions contain `digest(` and `'sha256'` |
| U-C18 | `crdb_full_text_search` | REPO | SQL: `information_schema.columns WHERE data_type='tsvector' AND is_generated='ALWAYS'` → **1** |
| U-C19 | `crdb_partial_indexes` | REPO | SQL: `count(*) FROM pg_indexes WHERE indexdef ILIKE '%WHERE%'` → **6**; split on `CREATE UNIQUE` → **2** |
| U-C20 | `crdb_inverted_indexes` | REPO | SQL: `count(*) FROM pg_indexes WHERE indexdef ILIKE '%USING gin%'` → **5** |
| U-C21 | `crdb_storing_indexes` | REPO | SQL: `count(*) FROM pg_indexes WHERE indexdef ILIKE '%STORING%'` → **9** |
| U-C22 | `crdb_composite_fk` | REPO | SQL: `count(*) FROM pg_constraint WHERE contype='f' AND array_length(conkey,1)>1` → **19**, of which 2 are three-column |
| U-C23 | `crdb_column_families` | REPO | `SHOW CREATE ALL TABLES` → `FAMILY ` present on **3** tables |
| U-C24 | `crdb_schema_locked` | REPO | count of `schema_locked = true` in `SHOW CREATE ALL TABLES` **equals** count of base tables → 89 = 89 |

### 4.2 CockroachDB — transaction semantics (7 more)

| # | proposed key | state | detector (exact) |
|---|---|---|---|
| U-T1 | `crdb_savepoint` **(new)** | LIVE | grep `ROLLBACK TO SAVEPOINT`, anchor `gate_run.py:671` |
| U-T2 | `crdb_read_committed` **(new)** | DECLARED | grep `READ COMMITTED`, anchor `cf45_read_committed.py:78`; verdict must carry "the case cannot build its world on the deployed schema" |
| U-T3 | `crdb_retry_40001` **(new)** | LIVE | grep `\b40001\b`, anchor `db.py:154`; artefact `evidence/deploy/cloud-contention.json` |
| U-T4 | `crdb_hlc_builtin` **(new)** | LIVE | grep `cluster_logical_timestamp\(\)`, anchor `gate_run.py:374` |
| U-T5 | `crdb_internal` **(amend: split the existing row)** | NOT-AVAILABLE (schema) | grep `crdb_internal` over `verticals/mainline/apps/demo-api/src/` → **0 hits**, which is the finding; the row must stop conflating the restricted schema with the unqualified builtin (U-T4) |
| U-T6 | `crdb_no_advisory_locks` **(new)** | REPO | grep `schema_lock`, anchor `lock.py:5` |
| U-T7 | `crdb_multi_region` **(new)** | NOT-AVAILABLE | grep `REGIONAL BY\|SURVIVE .*FAILURE\|ADD REGION` → **zero hits is the row's evidence**; plus `SHOW DATABASES` → `primary_region` NULL |

A NOT-AVAILABLE row has no anchor by construction, which is exactly why the pattern matters more
there than anywhere else.

### 4.3 AWS — proposed rows (10 + 3 amendments)

| # | proposed key | state | detector (exact) |
|---|---|---|---|
| U-A1 | `aws_lambda_function_url` **(new; today it is folded into `aws_lambda`)** | LIVE | HTTP: unauthenticated `GET {origin}/v1/health` → **200** (a 403 would mean `AWS_IAM`); repo: `grep -c 'authorization_type = var.url_authorization_type' infra/modules/demo-api/main.tf` == 1 |
| U-A2 | `aws_cloudwatch_logs` **(new; split out of `aws_cloudwatch`)** | LIVE | repo: `aws_cloudwatch_log_group.this` and `logging_config.log_group` referencing it; HTTP: `x-amzn-requestid` header present. **Reading an event needs the account and the detector must not claim more** |
| U-A3 | `aws_sigv4_no_sdk` **(new; a technique, not a service)** | LIVE | `grep -c boto3 …/mainline_demo_api/*.py` == 3 **and all three are comments**; `pytest …::test_no_web_framework_or_aws_sdk_is_imported` → 1 passed |
| U-A4 | `aws_live_transcript_identity` **(new)** | LIVE | `GET {origin}/v1/health`'s `schema_fingerprint` **equals** `evidence/demo/memory-loop.json → deployment.body.schema_fingerprint`; and every record in `evidence/demo/live-beats.json → requests[]` has a distinct `request_id` with `emulator_header == null`. **The cheapest guard in this table**: it fails loudly the day the deployed database stops being the one the evidence describes |
| U-A5 | `aws_sns` | APPLIED | `grep -c 'resource "aws_sns_topic"' infra/modules/cost-guard/main.tf` = 1, plus the 13 addresses at `evidence/deploy/cost/plan-shape.json#/resources/module.guard[0]` |
| U-A6 | `aws_budgets` | APPLIED | `grep -c 'resource "aws_budgets_budget"'` = 1; limit from `budget_limit_usd` default |
| U-A7 | `aws_cloudwatch_alarms` | APPLIED | `len(plan-shape.json#/alarms)` = **7** |
| U-A8 | `aws_cloudwatch_dashboard` | APPLIED | `sed -n '841,978p' infra/modules/demo-api/main.tf \| grep -cE '^\s+type\s+='` = 5 widgets |
| U-A9 | `aws_lambda_cost_guard` | APPLIED | `grep -rn 'resource "aws_lambda_function"' infra --include=*.tf` returns **2** |
| U-A10 | `aws_s3_tfstate` | APPLIED | `evidence/deploy/APPLIED.md:23-25`; `grep -n 'use_lockfile' infra/envs/demo/backend.tf` |
| U-A11 | `aws_service_quotas` | REPO | `alarm-reachability.json#/account_facts_measured/…/Value` = 10.0 |
| U-A12 | `aws_cost_explorer` | REPO | `aws-quota-and-cost.json#/part_4_account_spend_context/command` is a real `aws ce get-cost-and-usage`; `#/part_2b_the_budget/budget_actions_across_all_three` = **0** across **3** pre-existing budgets |
| U-A13 | *(amend)* `aws_cloudwatch` | REPO | keep the read-only metric census and **retitle it**: its verdict basis is the Bedrock metric read, and its title claims alarms it does not measure — and undercounts them. See over-claim O1 |

**Route census as a free detector.** `GET /v1/` returns a 404 that enumerates every declared
resource, derived from the router rather than maintained beside it, so
`len(json['error']['declared']) == 17` self-updates instead of drifting. One request, no
credential, and a judge holds the whole public surface.

---

## 5. THE OVER-CLAIM LIST — what a document asserts that a worker could not verify

Every entry names who found it and what the honest version is. **Nothing in O1–O17 was fixed by the
worker who wrote them**: four of the files involved are ratchets, generators or evidence, and the
rest are outside W7's two owned paths. **O18 and O19 are different — they were struck by the
2026-08-16 adversarial audit against *this page*, and both are fixed here**, in the two places this
page owns.

| # | the claim | where it lives | what was measured | disposition |
|---|---|---|---|---|
| **O1** | `aws_cloudwatch` EXERCISED, titled *"logs, four alarms, one dashboard"* | `evidence/tool-usage/aws-services.json` | its EXERCISED basis is the **read-only Bedrock metric census** and says so at length; there are **7** alarms, not four; and no alarm or dashboard has ever been read back out of CloudWatch | **Retitle and split** into U-A2 / U-A7 / U-A8 / U-A13. The verdict is defensible; the title is not |
| **O2** | `aws_eventbridge` DESIGNED | same file | `grep -rn "aws_cloudwatch_event\|aws_scheduler" infra --include=*.tf` returns **no output** — there is no resource to have designed | **Downgrade the basis** to the absence grep; **drop from the close block** (W2's recommendation, carried) |
| **O3** | *"`crdb_internal` for the HLC ordering the ledger"* | `docs/submission/DEVPOST.md:124` | the qualified spelling returns **42883 unknown function**; the builtin is unqualified `cluster_logical_timestamp()`, and the schema is refused **42501** by platform default | **Rewrite that clause.** Outside W7's owned files; escalated as E-4 |
| **O4** | *"the brief's 5 live VECTOR columns"* | the task brief; any document inheriting it | **4** `VECTOR` + **1** `TSVECTOR`, measured twice today | **Corrected upward** by R8, §0. The right claim is stronger than the wrong one |
| **O5** | *"59 triggers"* said flat | the plan §2 priority list | 39 trigger **objects** over 59 (trigger, **event**) pairs | **Say both numbers.** A judge running the obvious count gets 39 |
| **O6** | *"ten tables refuse mutation outright"* | the plan §2 | **17** tables carry `fn_refuse_mutation`; an eighteenth is append-only under a stricter guard | **Corrected upward** (PL4) |
| **O7** | `crdb_managed_mcp` EXERCISED | `evidence/tool-usage/crdb-features.json` | **sustained** — two transcripts, five days apart | **Keep**, and carry 15/16, `DIVERGED — KNOWN GAP` and `credential_publishable: false` every time |
| **O8** | `crdb_follower_reads` EXERCISED | same file | **sustained** — the cluster test passed today, `tests=3 failures=0 errors=0 skipped=2` | **Keep.** Its CI skip is a named skip for a missing cluster, not an absent capability |
| **O9** | `0034_event_edge.sql` listed as a recursive-CTE site | the plan §2 item 13 | its `WITH RECURSIVE` is inside a `--` comment block; `grep -vE "^\s*--" … \| grep -c RECURSIVE` → **0** | **Claim removed.** The executable sites are elsewhere and there are four of them |
| **O10** | detector `statement_refs[]` on `POST /v1/demo/gate-run` | `census/crdb-programmable.md` §5 | the live response has **no `statement_refs` key**; each beat carries `statement` | **Detector corrected** in U-C15 |
| **O11** | *"the alarms are declared in Terraform and have not been created"* and *"2 AWS services marked as having run"* | `docs/submission/VIDEO-KIT.md:250, 260` | the apply of 2026-08-14 created them; six AWS rows are EXERCISED today | **Stale, and it under-claims.** Outside W7's owned files; escalated as E-5 |
| **O12** | *"All still DESIGNED; `terraform apply` has never been run"* | `docs/HONESTY.md:1120` | `evidence/deploy/APPLIED.md:14` — *24 created, 0 changed, 0 destroyed*. Lambda, IAM, SSM and CloudWatch-as-infrastructure are in the account; S3-as-evidence-store, KMS, CloudTrail, CloudFront and EventBridge are still uncreated | **One clause, not the row.** `HONESTY.md` may not be edited by this worker (standing prohibition 6); escalated as E-3 with the replacement clause written out |
| **O13** | *"There is no public demo origin"*, and `SUBMISSION.json` holds `demo_url: UNRESOLVED` | `MUST-NOT-CLAIM.md` §12; `VIDEO-KIT.md` §"The demo URL" | measured today: `SUBMISSION.json` **carries the hostname**, and the origin answers 200 with `ok true`. **The prohibitions in that family are untouched and still correct** — both acceptance artefacts were taken over a local emulator socket and neither proves the origin | **The register is right about what it forbids and stale about one premise.** `MUST-NOT-CLAIM.md` may not be edited by this worker; escalated as E-2 |
| **O14** | *"policy-as-code enforces the custody controls"* if said without qualification | any reading of RP5 | the 596 lines of Rego have **never been executed**; the gate that runs and has been observed refusing is the Python one, 15 rules | **Say the gate that runs** (RP5's wording) |
| **O15** | KMS on the live request path | implied by `WithDecryption: true` + the `kms:Decrypt` grant | the applied parameter's **type was never read back**; if it is a plain String, no KMS call happens | **Recommended default: leave KMS out of the close block.** One read-only command settles it — escalation E-1 |
| **O16** | evidence files that a judge will open and misread | `evidence/deploy/verify/post-apply-dry.json` (verdict `NOT SATISFIED`, 0 of 9) and `evidence/demo/judge-path-walk.json` (verdict `INCOMPLETE`) | both are superseded **in fact** by `evidence/demo/live-beats.json` (verdict `PROVEN`, `failures: []`) and by the apply — **but not in filename** | **No claim on this page depends on either.** A dated pointer in the place a judge looks first would close it; escalated as E-6 |
| **O17** | *"these screens are the deployed console"* | the film uses `evidence/demo/operator-capture.json` | the capture states its own target: `base_url http://127.0.0.1:8741`, `emulator_header local_furl`, `is_the_deployed_url false` | **Say "filmed against a local emulator of the Function URL running the same handler."** The emulator imports the same handler module, so the screens are honest about the *application* and are not evidence about AWS |
| **O18** | PL10's `verify in 60s` predicate — a `LIKE` prefix-match on the `mainline` name, answered *"nine rows, `rolcanlogin` false on all nine"* | **this page, PL10** (and `census/close-block.md:246`, not owned here) | that predicate returns **5** rows, `rolcanlogin` **true** on `mainline_api` and `mainline_judge` — so the published check refuted the published answer using the login this submission hands judges. The nine-name `IN` list at `census/crdb-programmable.md:827` returns **9 rows, `f` on all nine** | **FIXED HERE, 2026-08-16.** Predicate restored to the `IN` list with `ORDER BY 1`; the answer is unchanged at nine and is **not** softened to five, and `LIKE 'agent\_%'` is not substituted (it returns **10**). Output pasted under PL10 |
| **O19** | CT4 Agent Skills carried as **REPO**, promoting the generator's `DESIGNED` | **this page, CT4 and U-C4** (and `census/crdb-four-tools.md` §4.1, also owned) | `evidence/tool-usage/crdb-features.json` → `rows.crdb_agent_skills.verdict` prints **`DESIGNED`**; no run of either assertion script is captured under `evidence/`. The promotion rested on a CI lane whose recorded green is at `2dc5c86`, five commits behind | **FIXED HERE, 2026-08-16 — downward.** CT4 is DESIGNED, U-C4 proposes the detector without asserting the state, the totals move 24→23 REPO and 7→8 DECLARED, and **no run was captured to promote the row.** Three of four tools carry a transcript against a floor of two |

---

## 6. DIFF AGAINST `MUST-NOT-CLAIM.md`, FAMILY BY FAMILY

The register is fourteen families and nine scanner rules; four families have no rule at all and a
human is the only control. This census was read against all fourteen.

| family | does anything on this page or in the close block collide? |
|---|---|
| 1 · Data residency | **No.** RP2 states inference Sydney / database Singapore and names the tier reason. The forbidden phrasing appears nowhere. |
| 2 · Timings | **No.** No latency number appears on this page or in the close block. The live samples W1 measured are explicitly not a performance claim and are not carried here. |
| 3 · The corpus | **No** — and the close block carries the synthetic line itself rather than leaving it to the watermark. |
| 4 · Model behaviour | **No.** RP1 says cassettes replay to a byte-identical **decision**; it makes no claim about a live model today. |
| 5 / 10 · Conformance | **Guarded.** TX3's row names a case that **cannot build its world**, and says the number of blocked cases comes from the project's own census. No sentence anywhere claims that suite passes or has been demonstrated. The word *demonstrated* is used of the **MCP transcript** (R1), which is a different artefact and a true one. |
| 6 · The chain count | **Guarded.** `271 / 271` is only ever quoted as *what that request returned today*, from `/v1/health`, re-derived rather than recalled, and TX10 says it is a chain-ledger count and not a pass-rate. |
| 7 · Ledger keys | Not touched by this census. |
| 8 · Custody bundle | **Guarded.** DC3 quotes `passed 9, failed 0, not_checked 7, exit_code 2` and says what is checked is the Merkle structure. |
| 9 · CockroachDB Cloud | **Guarded.** CT3 and CT4 both say no automated lane has ever pointed at the managed cluster and that the transcript is a human session. |
| 11 · The MI ratchet | Not quoted anywhere on this page. If it is wanted, run the ratchet and read its last line. |
| 12 · The acceptance run | **One premise in the register is stale and the prohibitions are not.** See over-claim O13 and escalation E-2. Nothing here cites `acceptance.json` or `cloud-acceptance.json`; the live-origin rows cite `/v1/health`, `/v1/demo/gate-run`, `live-beats.json` and `memory-loop.json`, which are HTTP transcripts of the origin itself. |
| 13 · The vocabulary digest | Not claimed on this page. |
| 14 · Where the defeater refusal lives | **Guarded by omission and worth stating once:** `mainline.disposition` has **no** foreign key onto `mainline.defeater_option`, so that particular refusal is the application's. No row on this page claims it as the database's, and the close block's "the database refuses" lines are PL4, PL8, SC4, SC10 and TX1 — each of which is a trigger, a policy, a unique index, a foreign key or an isolation level. |
| MNC-01 · RLS | **Guarded.** PL8's never-say names the rule rather than repeating the banned phrasing. |
| MNC-06 · Rubber-stamping | Not claimed. The film's own limit card carries it. |
| MNC-10 · ANN replay | Not claimed. CT2 claims a refusal (42809) and a plan, never a bit-identical result. |
| MNC-15 · Upstream | **Guarded.** CT4 says staged and not filed, and claims the filing never the merge. |

---

## 7. ESCALATIONS — undecidable here, for the founder (ruling R7)

Nothing below was acted on. Each needs a credential, an apply, a grant change, or an edit to a file
this worker may not touch.

**E-1 · Is the applied SSM parameter a `SecureString`?** If yes, KMS is genuinely on the cold-start
path and earns a row; if it is a plain `String`, `WithDecryption` is ignored and **KMS must not
appear in the close block at all**. One read-only command settles it and prints the *type*, never
the value: `aws ssm describe-parameters --parameter-filters "Key=Name,Values=/mainline/demo/cockroach_dsn"
--query 'Parameters[].[Name,Type]' --output text`. **Recommended default if nobody runs it: leave
KMS out.** The close block already does.

**E-2 · `MUST-NOT-CLAIM.md` §12 carries a premise the apply falsified** — *"There is no public demo
origin"* — while every prohibition in that family remains correct and load-bearing. The narrow fix
is one clause: the acceptance artefacts are still local-socket and still prove a handler rather
than an origin; what changed is that an origin now exists and is evidenced by different artefacts.
**Standing prohibition 6 forbids this worker from editing that file.**

**E-3 · `docs/HONESTY.md:1120` says `terraform apply` has never been run.** It has. The replacement
clause a maintainer could paste, from W2: *"All were DESIGNED when this row was written; the apply
of 2026-08-14 created Lambda, IAM, SSM and CloudWatch — S3-as-evidence-store, KMS, CloudTrail,
CloudFront and EventBridge are still DESIGNED."* This matters more than a normal stale line because
of **where it is**: a sceptical judge goes to `HONESTY.md` first, and the one sentence there that is
out of date is a sentence that **under-claims**. Verify in 20 s: `sed -n '1120p' docs/HONESTY.md`
beside `sed -n '14p' evidence/deploy/APPLIED.md`.

**E-4 · `DEVPOST.md:124`** says *"`crdb_internal` for the HLC ordering the ledger"*. Over-claim O3;
the true clause is *"the unqualified `cluster_logical_timestamp()` builtin for the HLC ordering the
ledger — the `crdb_internal` schema itself is refused 42501 on this version."*

**E-5 · `VIDEO-KIT.md` §§ "Do NOT say CloudFront" and "Do NOT name an AWS service…" are stale in the
direction that under-claims** — they say the alarms are not created and that two AWS services have
run. Six have. The CloudFront prohibition itself is correct and must stay.

**E-6 · Two evidence files carry red verdicts that no claim depends on**
(`post-apply-dry.json` → `NOT SATISFIED 0 of 9`, a *pre*-apply dry run; `judge-path-walk.json` →
`INCOMPLETE`, a local walk). Both are superseded in fact and not in filename. A dated pointer where
a judge looks first would close it; renumbering or editing an evidence record must not be done.

**E-7 · The MCP `N01` divergence.** The `managed-mcp` identity reads a `mainline_qa` view the pack
asserted it could not. Closing it means changing a grant on submission eve. **Standing prohibition:
never widen or narrow a database grant.** And a negative suite that has quietly gone green is the
worst artefact in a repository, because it reads as the strongest.

**E-8 · The `skills` lane's recorded green is at an older commit** than the tip that measured it. A
dispatch converts "green five commits ago" into "green at HEAD" and costs one click. CI state is
the orchestrator's.

**E-9 · The census prose ratchet does not reach `docs/submission/census/`.**
`check_submission_prose.py`'s target glob is `docs/submission/*.md` — **single level** — so this
file **is** scanned (and passes, §8) while its six sources are not. The recommended repair is one
character, `docs/submission/**/*.md`, but widening a ratchet's scope mid-submission may light up
files other workers are still writing. **Escalated rather than done.** W3 hand-scanned its own file
and found only the SHA-literal family, which the submission surface deliberately scopes out.

**E-10 · The standing `materialise_checks` / `exposure_receipt` INSERT gap stays open.** Widening
the write surface of an unauthenticated endpoint is the founder's call and he has not made it. Two
rows on this page (SC4, and part of PL4) name the gap in their own never-say lines rather than
working around it.

**E-11 · Nobody has read the applied AWS stack back.** `scripts/deploy/post_apply_verify.py` exists,
declares 9 checks, and has only ever run in dry mode before the apply. The **safe half** — the alarm
inventory with the kill-switch leg in dry mode, no stop — would turn every APPLIED row in §2.6 from
*"the apply says so"* into *"the account says so"*, for a few minutes of read-only calls. Founder's
call; out of scope by construction here.

---

## 8. PROVENANCE — everything this worker ran

Run 2026-08-16 from `D:/CoackroachDBxAWS/mainline`. `$ORIGIN` is the demo hostname in
`docs/submission/SUBMISSION.json`.

| # | command | what it printed |
|---|---|---|
| 1 | `GET $ORIGIN/v1/health` | `ok True · CockroachDB CCL v26.2.5 · mainline_demo · 271 / 271 · fingerprint ec9b1ce7…` |
| 2 | `POST $ORIGIN/v1/demo/gate-run` (×2, the second dumping beat shapes) | `verdict PROVEN`, 4 beats, `isolation SERIALIZABLE`, opened == closed logical timestamp, `persistence_check.identical true`; beat 2 `23514 gate_closed_when_issued` with `statement` = `CALL mainline.merge_permit(…)`; beat 3 `P0001 mainline.fn_permit_merge_gate` with `naa null`, `naa_reason not_computable`; **no `statement_refs` key anywhere** (over-claim O10) |
| 3 | `cockroach sql -d mainline_demo` — one probe, eight sub-selects | `fns 26 · procs 2 · trg_objects 39 · trg_pairs 59 · rls 4 · rls_force 4 · policies 25 · enum_labels 36` |
| 4 | `cockroach sql -d mainline_demo` — one probe, eight sub-selects | `vec_cols 4 · tsv_cols 1 · cspann 3 · generated 8 · partial_idx 6 · gin_idx 5 · composite_fk 19 · checks 461` |
| 5 | `python -c …` over `evidence/deploy/judge-run.json`, `evidence/mcp/pack-run.json`, `evidence/mcp/session.json` | `15 / 16 DIVERGED — KNOWN GAP` twice, `managed-mcp`, `cockroachdb-cloud 1.0.0`, 12 tools, `publishable False` |
| 6 | `python -c …` over both `evidence/tool-usage/*.json` | 12 AWS rows (6 EXERCISED / 5 DESIGNED / 1 NOT-AVAILABLE); 14 CockroachDB rows (12 EXERCISED / 2 DESIGNED) |
| 7 | `python scripts/submission/check_submission_prose.py` | `claim hygiene OK` · `scanned 19 file(s)` · `submission prose OK`, **exit 0**. The count moved from 18 to 19 because **this file is on that scanner's surface** — `docs/submission/*.md` reaches it — so it had to pass the nine SUB rules and the claim-hygiene table, and it does |
| 8 | `python scripts/demo/claim_hygiene.py --check` on **each** of the two files this worker wrote | `scanned 1 file(s) against 21 rules · claim hygiene OK`, twice, exit 0 — including `HYG-sha-literal`, which the submission surface scopes out and which this hand-scan therefore applied anyway |
| 9 | `pytest tests/deploy/test_docs_are_true.py -q --junitxml` | `tests=54 failures=0 errors=0 skipped=0` |
| 10 | `pytest tests/deploy/test_cost_model.py -q --junitxml` | `39 passed` |
| 11 | `pytest tests/release/test_honesty_is_checkable.py -q --junitxml` | `34 passed` |
| 12 | live spot-checks of three close-block lines: `GET $ORIGIN/v1/permits/{permit_id}`, `…/blocking-checks`, and `precondition {` in the demo-api module | **7** reflected CHECK constraints, named; a 64-hex `dedupe_key` beginning `c4bd7e3a…`; **7** precondition blocks |

**The full suite was not re-run and this line says so rather than implying it.** The baseline is
1070 collected / 1069 passed / 0 failed / 0 errors, and it cannot move from here by construction:
this change adds two Markdown files and touches no code, no test, no fixture and no threshold.
`DEFAULT_MAX_RESPONSE_BYTES`, the console bundle-headroom guard and the gate proof were not
approached. The two documentation ratchets that scan `docs/submission/` use **explicit path
allowlists** (`tests/deploy/test_cost_model.py:119-126`, `tests/deploy/test_docs_are_true.py:1361-1371`)
which name neither new file, and all three ratchets above are green with both files present.

**What this worker did not do.** No `terraform apply`, no `terraform` at all, no redeploy, no AWS
API call, no SSM read or write, no credential read or printed, no account id anywhere on this page.
No grant widened or narrowed. No commit. **No generator, ratchet or honesty document edited** —
`scripts/submission/capture_tool_evidence.py`, `HONESTY.md`, `CI-STATE.md` and `MUST-NOT-CLAIM.md`
were read only. No `continue-on-error`, no `|| true`. Two files written:
`docs/submission/feature-census.md` and `docs/submission/census/close-block.md`. No scratch database
was needed: every cluster probe is a `SELECT` over a catalog.

### 8.1 · Amendment, 2026-08-16 — the close-card wave (worker W5)

Two findings of the adversarial audit landed on this page: **S1**, PL10's role predicate, and the
Agent Skills state (O18 and O19 in §5). Both are fixed above. Everything run for that amendment,
from the same working directory:

| # | command | what it printed |
|---|---|---|
| A1 | `cockroach sql -d mainline_demo` — the nine-name `IN` list with `ORDER BY 1` | **9 rows**, `rolcanlogin` `f` on every one — pasted in full under PL10 |
| A2 | the same query with a `LIKE` prefix-match, run **once, to confirm the strike** | **5 rows**; `mainline_api` **t**, `mainline_judge` **t**, the other three `f`. This is why the predicate was replaced and why the answer was **not** softened to five |
| A3 | `cockroach sql -d mainline_demo` — `pg_indexes ILIKE '%cspann%'`; `information_schema.columns` where the type is vector-ish | **3** `cspann` indexes; **4** `vector` columns + **1** `tsvector` — the numbers the `k3` card prints, re-confirmed rather than copied |
| A4 | `grep -c 42809 evidence/aws/ann/explain-unhinted.txt`, then `grep -n "REFUSED BY THE SERVER"` | **3** occurrences of `42809`; the refusal itself at **`:205`** and **`:220`** |
| A5 | the four card one-liners, verbatim (§0.1.1 of `census/crdb-four-tools.md`) | `15 / 16 DIVERGED — KNOWN GAP` · two `SQLSTATE 42809` lines · `['v26.2.5']` · **`DESIGNED`** |
| A6 | `python scripts/submission/check_submission_prose.py` | `claim hygiene OK` · `submission prose OK`, **exit 0**, with both amended files present |
| A7 | `python scripts/demo/claim_hygiene.py --check` on each amended file | `docs/submission/feature-census.md` → **3** findings, all `HYG-sha-literal`, all three the same stale-green skills commit — the one that now holds CT4 at DESIGNED; `census/crdb-four-tools.md` → **14**, all `HYG-sha-literal`. **Zero findings in any other family, including every must-not-claim rule.** `HYG-sha-literal` is the family the submission surface deliberately scopes out — a provenance disclosure's job is to quote git commits — and A6, the governing scan for `docs/submission/*.md`, exits 0. This row does not itself quote the commit, so the count it states stays true of the page that states it |
| A8 | `pytest tests/deploy/test_docs_are_true.py tests/deploy/test_cost_model.py tests/release/test_honesty_is_checkable.py -q --junitxml` | **`tests=127 failures=0 errors=0 skipped=0`**, read out of the junit XML rather than off a terminal tail |

**Every amendment in this wave moves a claim down or holds it flat. None moves one up.** The role
count stays at nine because nine is what the correct predicate returns; Agent Skills goes from REPO
to DESIGNED; the REPO total goes 24 → 23. **No run under `evidence/` was captured, generated or
committed to promote a row, and no file under `evidence/`, `skills/` or `infra/` was written.** No
`terraform`, no AWS call, no SSM access, no credential, no grant change, no commit. The film is not
lengthened by anything on this page — 172 s total against a 174 s hard stop — because a card line
costs layout, not seconds.
