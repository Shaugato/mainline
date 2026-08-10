<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# TOOL USAGE — which CockroachDB and AWS services, and how

This is the hackathon's *"documentation of which CockroachDB and AWS services were used
and how"*. The bar is **at least two CockroachDB tools and at least one AWS service**.
MAINLINE documents
4 [src: evidence/tool-usage/crdb-features.json#totals.by_kind.tool] CockroachDB tools —
inside which 10 [src: evidence/tool-usage/crdb-features.json#totals.by_kind.feature]
engine features are separately accounted, because counting a feature as a tool to clear a
bar is the kind of arithmetic this repository exists to refuse — and
12 [src: evidence/tool-usage/aws-services.json#totals.by_kind.service] AWS services.

It is written to be **checked line by line, not read**. Every count below carries a
`[src: …]` reference in the style of [`docs/HONESTY.md`](HONESTY.md), every mechanism
carries a file and a line number, and every entry carries a verdict saying whether the
thing has actually run.

```bash
python scripts/submission/capture_tool_evidence.py --check   # exit 1 if any number here is stale
```

That command is standard-library only, takes no network and no credential, and re-derives
both evidence files from the tree. A document about which cloud services a project uses
must not require those cloud services in order to check it.

**One convention, borrowed from `docs/HONESTY.md`.** A bare number carries a `[src: …]`
reference to a committed artefact. Digits inside `code spans` are **names**, not
measurements — `v26.2.5`, SQLSTATE `23514`, a byte cap of `10240` read from a named line
of source. And the blocks headed *"Measured on the pinned local node"* are transcripts of
a scratch run against the local single-node cluster; they are **reproducible, not
committed** — no artefact under `evidence/` records them, and no number in any table here
depends on one. Part 5 gives the commands.

---

## The verdict column, and why the third value exists

| verdict | means |
|---|---|
| **EXERCISED** | it ran, and a committed artefact in this repository records the result |
| **DESIGNED** | the code or configuration is complete and on disk; nothing recorded has run it end to end |
| **NOT-AVAILABLE** | checked on this platform and absent; no dependency was taken on it |

Counted across both censuses: EXERCISED
11 [src: evidence/tool-usage/crdb-features.json#totals.by_verdict.EXERCISED]
+ 0 [src: evidence/tool-usage/aws-services.json#totals.by_verdict.EXERCISED],
DESIGNED 3 [src: evidence/tool-usage/crdb-features.json#totals.by_verdict.DESIGNED]
+ 11 [src: evidence/tool-usage/aws-services.json#totals.by_verdict.DESIGNED],
NOT-AVAILABLE 1 [src: evidence/tool-usage/aws-services.json#totals.by_verdict.NOT-AVAILABLE].

**Read that asymmetry rather than skipping it.** The CockroachDB half has run. The AWS
half has **nothing** in the EXERCISED column: the account is live and the models are
enabled, but every code path to them is a recorded cassette and every Terraform module is
unapplied. A submission document that flattened both halves into "used" would be lying
about the more important one. See [`docs/HONESTY.md`](HONESTY.md).

**Scan set for every count below**: a filesystem walk of
7233 [src: evidence/tool-usage/crdb-features.json#scan.files_scanned] text files, caches
and build output pruned, of which
271 [src: evidence/tool-usage/crdb-features.json#scan.files_by_category.migration] are
migrations and 25 [src: evidence/tool-usage/crdb-features.json#scan.files_by_category.terraform]
are Terraform/Rego. `file_count` counts where a feature is used **and** where it is
discussed, which is why every row also names one hand-checked file and line. The census
refuses to write if any of those citations stops resolving.

---

# Part 1 · CockroachDB — four tools

## Tool 1 · CockroachDB itself (v26.2.5)

**The product's central claim is a database refusal, so the database is not a datastore
under this system — it is the system.** MAINLINE gates the merge of a permit-to-work: a
permit may not reach `merged` while a recalled precursor carries an obligation nobody has
signed off. That rule is enforced by constraints and triggers, so it holds against psql, a
migration script and a back-office correction alike — not only against the application
that was written to respect it.

**Where it runs.** A local single-node `cockroachdb/cockroach:v26.2.5` pinned at
`compose.yaml:31`, and CockroachDB Cloud Basic cluster `mainline-dev` in
`aws-ap-southeast-1` (Singapore). The pinned version string appears in
266 [src: evidence/tool-usage/crdb-features.json#rows.crdb_database.file_count] files.

### The exhibit: three beats, one committed transcript

`scripts/proof/gate_refusal.py` builds a schema, replays illegal histories, and writes
[`evidence/gate-refusal/proof-20260810T004200Z.json`](../evidence/gate-refusal/proof-20260810T004200Z.json).

| beat | outcome | SQLSTATE | exhibit |
|---|---|---|---|
| plain CHECK | REFUSED | `23514` [src: evidence/gate-refusal/proof-20260810T004200Z.json#refusal.sqlstate] | `gate_closed_when_issued`, source `reported` |
| **forged projection** | REFUSED | `P0001` [src: evidence/gate-refusal/proof-20260810T004200Z.json#drift_refusal.sqlstate] | `mainline.fn_permit_merge_gate`, source `parsed` |
| after one signed disposition | ADMITTED | `00000` [src: evidence/gate-refusal/proof-20260810T004200Z.json#admission.sqlstate] | `merge_record` with a server-computed clearance digest |

Verdict on the run: `PROVEN` [src: evidence/gate-refusal/proof-20260810T004200Z.json#verdict].

**The middle beat is the one to read twice.** The projected counter was set to zero out of
band — the exact attack a "materialised conflict" design must survive — and the gate
refused anyway, because it **re-derives** the obligation count instead of trusting the
column it is handed. P2 projections are enforced, never trusted. The third beat matters
just as much: a gate that always refuses is broken, not safe.

That run measured a tree of
261 [src: evidence/gate-refusal/proof-20260810T004200Z.json#chain.files] migration files
with 246 [src: evidence/gate-refusal/proof-20260810T004200Z.json#chain.applied_count]
applied and 15 [src: evidence/gate-refusal/proof-20260810T004200Z.json#chain.failed_count]
failing, every failure attributable to a named table with no producer migration and
0 [src: evidence/gate-refusal/proof-20260810T004200Z.json#chain.failures_unexplained|len]
failures unexplained. **That is a snapshot of `2026-08-10T00:42:10Z`, not a statement about
the tree today** — the tree now holds
271 [src: evidence/tool-usage/crdb-features.json#scan.files_by_category.migration]
migration files, and re-running the proof is the only honest way to update those three
numbers.

### The engine features, and what each one is doing here

| feature | verdict | files | anchor |
|---|---|---|---|
| SERIALIZABLE isolation | EXERCISED | 128 [src: evidence/tool-usage/crdb-features.json#rows.crdb_serializable.file_count] | `packages/trappoint-model/src/trappoint_model/cluster.py:222` |
| PL/pgSQL triggers & functions | EXERCISED | 118 [src: evidence/tool-usage/crdb-features.json#rows.crdb_triggers.file_count] | `verticals/mainline/db/migrations/0115_fn_permit_merge_gate.sql:77` |
| Named CHECK constraints | EXERCISED | 156 [src: evidence/tool-usage/crdb-features.json#rows.crdb_check_constraints.file_count] | `verticals/mainline/db/migrations/0050_permit.sql:114` |
| C-SPANN vector index | EXERCISED | 116 [src: evidence/tool-usage/crdb-features.json#rows.crdb_vector_index.file_count] | `verticals/mainline/db/migrations/0031_clause_embedding.sql:149` |
| `AS OF SYSTEM TIME` | EXERCISED | 62 [src: evidence/tool-usage/crdb-features.json#rows.crdb_as_of_system_time.file_count] | `packages/trappoint-conformance/cases/cf46_time_travel_cannot_reach.py:106` |
| Follower reads | EXERCISED | 9 [src: evidence/tool-usage/crdb-features.json#rows.crdb_follower_reads.file_count] | `verticals/mainline/db/migrations/0180c_role_agent_patroller.sql:37` |
| Row-level security | EXERCISED | 38 [src: evidence/tool-usage/crdb-features.json#rows.crdb_row_level_security.file_count] | `verticals/mainline/db/migrations/0181a_permit_rls_force.sql:54` |
| `SHOW CREATE` self-attestation | EXERCISED | 54 [src: evidence/tool-usage/crdb-features.json#rows.crdb_show_create.file_count] | `packages/trappoint-migrate/src/trappoint_migrate/attest.py:243` |
| `crdb_internal` | EXERCISED | 59 [src: evidence/tool-usage/crdb-features.json#rows.crdb_internal.file_count] | `packages/mainline-mcp/src/mainline_mcp/limits.py:75` |
| CHANGEFEED / CDC | **DESIGNED** | 3 [src: evidence/tool-usage/crdb-features.json#rows.crdb_changefeed.file_count] | `verticals/mainline/db/migrations/0168_v_changefeed_health.sql:37` |

Now the *how*, which is the part the rule actually asks for.

#### SERIALIZABLE — because the gate reads before it writes

`verticals/mainline/db/migrations/0115_fn_permit_merge_gate.sql:56` reads the projected
counter, re-derives the true count, and then permits or refuses a write. Under anything
weaker than SERIALIZABLE that read-then-write pair is a write-skew hole, and the whole
safety claim leaks through it. So isolation is **set explicitly on the connection**
(`packages/trappoint-model/src/trappoint_model/cluster.py:222`) rather than inherited as a
default that a future cluster setting could change underneath us, and the conformance
harness retries `40001` and nothing else
(`packages/trappoint-conformance/src/trappoint_conformance/sqlstate.py:38`) — a blanket
retry helper is a forbidden import repo-wide, because retrying a constraint violation is
how a refusal becomes a delay.

*Measured on the pinned local node.* `SHOW default_transaction_isolation` →
`serializable`, and — more to the point, because a reported isolation level is not a
refusal — a write-skew pair was **refused**:

```
A: BEGIN; SELECT sum(v) FROM ledger        -> 20
B: BEGIN; SELECT sum(v) FROM ledger        -> 20
A: UPDATE ledger SET v = 0 WHERE k = 1
B: UPDATE ledger SET v = 0 WHERE k = 2
A: COMMIT                                  -> ok
B: COMMIT                                  -> 40001 restart transaction:
                                              TransactionRetryWithProtoRefreshError
```

Two transactions reading an aggregate and each writing a different row is the textbook
anomaly the gate would be exposed to. The database refused it.

#### Triggers and PL/pgSQL — the gate is in the database, not in front of it

`verticals/mainline/db/migrations/0115_fn_permit_merge_gate.sql:77` is the `RAISE EXCEPTION USING ERRCODE = 'P0001'` that
produced the second beat of the proof; `verticals/mainline/db/migrations/0120_trg_check_project.sql:28` is the `BEFORE
INSERT` trigger that projects a cross-row fact onto a scalar column. Triggers are a v26.2
feature and the design depends on them existing: without them the projection would have to
be maintained by the application, which is the failure mode the product exists to remove.

One platform detail worth publishing because it cost real time:
`verticals/mainline/db/migrations/0115_fn_permit_merge_gate.sql:54` notes that the unparenthesised `NEW.col` read form does
not survive `CREATE TRIGGER` on v26.2.5, so every trigger body assigns `(NEW).col` to a
local first.

#### Named CHECK constraints — the constraint *name* is the deliverable

`verticals/mainline/db/migrations/0050_permit.sql:114`:

```sql
CONSTRAINT gate_closed_when_issued CHECK (state <> 'merged' OR open_blocking = 0),
```

A refusal with the right SQLSTATE and the wrong constraint name is the right outcome for
the wrong reason, so every conformance case asserts **both**, and the proof records
`constraint_source` as `reported` or `parsed` — `parsed` when the driver gave no
`diag.constraint_name` and the exhibit had to be recovered from the message, which is
always the case for `P0001`. Saying which is the difference between a diagnosis and a
guess.

#### C-SPANN vector index — recall and refusal in one transaction domain

`verticals/mainline/db/migrations/0031_clause_embedding.sql:149`:

```sql
VECTOR INDEX ce_ann (site_id, activity_root, embedding vector_cosine_ops),
```

Declared **inline at `CREATE TABLE`**, because on v26.2 building a vector index over an
already-populated table is the slow path; the table is created empty and loaded after.
Vectors live in sidecar tables, one embedding space each, because a table may carry only
one vector index.

*Measured on the pinned local node*, `500` rows in a table of this exact shape:

```
EXPLAIN … ORDER BY embedding <=> $1 LIMIT 5           →  no vector search in the plan
EXPLAIN … FROM clause_embedding@ce_ann … LIMIT 5      →  • vector search
                                                            table: clause_embedding@ce_ann
                                                            prefix spans: [/'…0001'/'hot-work' - /'…0001'/'hot-work']
```

**The index is chosen only when explicitly hinted**, and only with every prefix column
constrained to a single value. That is a platform fact with a design consequence: the
recall path writes the hint, and an ANN query that quietly fell back to a full scan would
otherwise be indistinguishable from one that did not.
`skills/designing-vector-recall-prefixes/scripts/assert_prefix_index_used.py` exists to
fail when the plan stops using the index.

#### `AS OF SYSTEM TIME` and follower reads — including where they stop

Two uses, and the second is the interesting one.

*Operationally*: fixity patrol and coverage scans read at `follower_read_timestamp()`
(`verticals/mainline/db/migrations/0180c_role_agent_patroller.sql:37`) so a background integrity sweep never contends with
a merge, and a patrol run that cannot state its follower-read timestamp is refused by its
own emitter.

*Epistemically*: `AS OF SYSTEM TIME` is **not** sold as "prove the state at time T".
`packages/trappoint-conformance/cases/cf46_time_travel_cannot_reach.py:106` is a
conformance case whose whole purpose is to show it cannot. The GC window on this cluster
is 4500 [src: evidence/gate-refusal/proof-20260810T004200Z.json#cluster.zone.gc_ttlseconds]
seconds — pinned locally to the Cloud value, so local is never more permissive than
production — and a query past it is **refused**, not silently answered from a truncated
history. Long-horizon reconstruction is the application-level commit DAG instead.

*Measured on the pinned local node.* `SELECT follower_read_timestamp()` returns; a count
`AS OF` that timestamp returns `500` rows; `ALTER DATABASE … CONFIGURE ZONE USING
gc.ttlseconds = 4500` applies and `SHOW ZONE CONFIGURATION` reads it back. And the far-past
read is refused:

```
SELECT count(*) FROM system.namespace AS OF SYSTEM TIME '-90m'    -> 3658 rows
SELECT count(*) FROM system.namespace AS OF SYSTEM TIME '-2160h'  -> XXUUU
                                                     "found no descriptor with id 1"
```

**Read that precisely.** What it shows is that a read far enough into the past is refused
rather than answered from a truncated history. It does **not** demonstrate the `4500`-second
boundary specifically — that is conformance case CF-46, and the conformance suite is in
**Part 4 · What is NOT claimed**.

#### Row-level security — FORCE, and no session variables

`verticals/mainline/db/migrations/0181_permit_rls_enable.sql:51` enables it;
`verticals/mainline/db/migrations/0181a_permit_rls_force.sql:54` **forces** it, so table owners are not exempt.
Policy expressions carry no subquery and no session variable — a session variable is client-settable, which would degrade RLS to an
application-cooperative control against exactly the adversary it is meant to constrain —
so the documented-safe shape is `USING (col = CURRENT_USER)` over a denormalised role
token.

The trap that this design has to survive is that with `FORCE` and SELECT-only policies the
default is DENY and **the gate locks itself out**, so every RLS-forced table a trigger
writes carries an explicit write policy. RLS is never enabled on the CDC source tables,
because changefeed queries fail on RLS-enabled and multi-family tables
(`verticals/mainline/db/migrations/0198x_no_rls_on_cdc_sources.sql`).

*Measured on the pinned local node:* after `ENABLE` + `FORCE` + one policy,
`pg_class.relrowsecurity` and `relforcerowsecurity` are both true and `pg_policy` holds
`('standing_owner_read', 'r', 'owner = current_user()')`.

#### `SHOW CREATE` — so the gate cannot be quietly edited

`packages/trappoint-migrate/src/trappoint_migrate/attest.py:243` fingerprints the live
schema from `SHOW CREATE ALL SCHEMAS / TYPES / TABLES` plus `pg_get_triggerdef()` and
`pg_get_functiondef()`, normalises (sort, collapse whitespace — intra-category ordering is
not guaranteed), hashes, and chains the hash into `trappoint.schema_attestation`. The
gate's **own source text** is therefore inside the attestation. `SHOW CREATE ALL TABLES`
omits routines, which is exactly why the `pg_get_*def()` half is there and why a fallback
to `SHOW CREATE TABLE` records `attestation_grade="weak"` in the row rather than pretending
equivalence.

*Measured on the pinned local node:* `SHOW CREATE TABLE` returned DDL naming the vector
index `ce_ann`.

#### `crdb_internal` — used by us, forbidden to the auditor

Two opposite uses, and the second is a security property.

*Internally*, `cluster_logical_timestamp()` is the HLC the sequencer orders appends by,
because `CREATE SEQUENCE` / `nextval` / `SERIAL` / `unique_rowid()` are banned repo-wide
(ADR `0045`). *Externally*, `crdb_internal` is on the MCP identity's forbidden list at
`packages/mainline-mcp/src/mainline_mcp/limits.py:75`, alongside `pg_catalog`,
`information_schema` and `pg_extension`. That it is **unreachable** over the audit surface
is what proves the `mainline_audit` views *are* the API rather than a bypass around one.

*Measured on the pinned local node, and it corrects two things worth publishing.*

```
SELECT count(*) FROM crdb_internal.tables            -> 42501 "Access to crdb_internal
                                                        and system is restricted"
SET allow_unsafe_internals = true; (same query)      -> 5642 rows
SELECT crdb_internal.cluster_logical_timestamp()     -> 42883 "unknown function"
SELECT cluster_logical_timestamp()                   -> 1786336392189292411.0000000000
```

First: on `v26.2.5` `crdb_internal` is **restricted by default**, and reaching it requires
opting in with `allow_unsafe_internals`. So the unreachability this design leans on is a
**platform default before it is a policy of ours** — which strengthens the claim rather
than weakening it. Second: the qualified spelling
`crdb_internal.cluster_logical_timestamp()` does not exist on this version; the builtin is
unqualified. `docs/adr/0045-cas-sequencing-not-sequences.md:142` uses the qualified form —
recorded here as a cross-domain note, and **not** edited, because that file is not this
document's to touch.

#### CHANGEFEED — DESIGNED, and deliberately not in a migration

`CREATE CHANGEFEED` appears in
3 [src: evidence/tool-usage/crdb-features.json#rows.crdb_changefeed.file_count] files and
has never been run. *Measured on the pinned local node:* the machinery is present and
idle — `SHOW CLUSTER SETTING kv.rangefeed.enabled` → `true`, `SHOW CHANGEFEED JOBS` → `0`
jobs.

That is a design decision before it is a gap: putting `CREATE CHANGEFEED` in a migration
makes migrations non-idempotent across a restore, so CDC is owned by the provisioning
agent, and the two migrations that exist —
`verticals/mainline/db/migrations/0155a_ops_changefeed_health_snapshot.sql` and
`verticals/mainline/db/migrations/0168_v_changefeed_health.sql:37` — observe changefeed health rather than start a
feed. The single CDC source table is `mainline_ops.outbox`, which is why RLS is forbidden
on it.

---

## Tool 2 · CockroachDB Cloud and the `ccloud` CLI — EXERCISED

**Verdict: EXERCISED.** [`evidence/ccloud/cluster-list.txt`](../evidence/ccloud/cluster-list.txt)
is a verbatim captured transcript of `ccloud auth whoami` followed by
`ccloud cluster list -o json`, ANSI spinner frames stripped and nothing else altered. The
term appears in 48 [src: evidence/tool-usage/crdb-features.json#rows.crdb_cloud_ccloud.file_count]
files across the tree.

```json
{ "name": "mainline-dev", "cockroach_version": "v26.2.5", "plan": "SERVERLESS",
  "cloud_provider": "AWS", "regions": [{ "name": "ap-southeast-1", "primary": true }],
  "config": { "serverless": { "spend_limit": 2500,
    "usage_limits": { "request_unit_limit": "100000000", "storage_mib_limit": "10240" }}}}
```

**How, specifically.** `-o json` is the point: the CLI is driven with structured output and
the JSON is **parsed, never screen-scraped**. `spend_limit: 2500` is the US$25.00 monthly
cap set at cluster creation — a ceiling, not a spend.

### Two measured limitations, published rather than worked around

**1 · `ccloud` 0.6.12 has no headless service-account authentication.**
`evidence/ccloud/README.md:37`. `ccloud auth` exposes only `login` / `logout` / `whoami`;
`login` is browser-based; `CC_API_KEY` in the environment is ignored; the cached session is
scoped to the interactive Windows logon and is not readable from a non-interactive shell.
`0.7.0`, `0.8.0`, `0.9.0` and `1.0.0` all `404` from `binaries.cockroachdb.com`, so
`0.6.12` is the latest published build.

**Therefore an agent cannot drive `ccloud` headlessly from a cold start, and MAINLINE does
not claim that it does.** Headless paths use the **CockroachDB Cloud REST API** with the
same service-account key, verified live against `/clusters`, `/clusters/{id}`,
`/service-accounts`, `/api-keys` and `/clusters/{id}/sql-users`.

**2 · Audit-log endpoints `404` on this tier.** `evidence/ccloud/README.md:46`.
`/auditlogentries`, `/auditlogs`, `/audit-logs` and the cluster-scoped variant all return
`404` on Basic/Serverless. The custody design's *"custody of the custodian"* mechanism —
folding control-plane audit records into the tamper-evident ledger — therefore has **no
input source on this tier**, and is documented as unavailable rather than shipped as an
unbacked claim.

---

## Tool 3 · CockroachDB Managed MCP Server — DESIGNED

**Endpoint** `https://cockroachlabs.cloud/mcp`, MCP **Streamable HTTP**, `Authorization:
Bearer <service-account key>`, and an `mcp-cluster-id` header pinning exactly one cluster —
a tool call naming a different cluster fails. All three constants are code, not prose:
`packages/mainline-mcp/src/mainline_mcp/limits.py:45` and `:48`.

**Verdict: DESIGNED.** The transport and the limit model are implemented and their offline
tests pass; **no live session against the managed endpoint is captured under `evidence/`**,
and `tests/integration/mcp` *skips with a reason* when no key is present rather than
passing vacuously. A green audit-surface run with nothing to talk to asserts nothing, and a
green *negative* run with nothing to talk to asserts the opposite of what it claims. The
MCP-facing surface — the client plus the `mainline_audit` schema it reads — appears in
160 [src: evidence/tool-usage/crdb-features.json#rows.crdb_managed_mcp.file_count] files.

### How: every documented limit is a type, not a comment

`limits.py` models the server's caps so a breach is refused **client-side** with an error
naming the limit, instead of arriving later as a truncated string:

| limit | value | line |
|---|---|---|
| statements per call | `1` | `packages/mainline-mcp/src/mainline_mcp/limits.py:54` |
| statement length | `16384` chars | `packages/mainline-mcp/src/mainline_mcp/limits.py:51` |
| request timeout | `20` s | `packages/mainline-mcp/src/mainline_mcp/limits.py:57` |
| **response cap** | **`10240` bytes** | `packages/mainline-mcp/src/mainline_mcp/limits.py:60` |
| SELECT rows, default / max | `25` / `10000` | `packages/mainline-mcp/src/mainline_mcp/limits.py:63`, `:66` |
| our own budget | `8192` bytes / `25` rows | `packages/mainline-mcp/src/mainline_mcp/limits.py:109`, `:112` |

**The `10 KiB` cap is the load-bearing one, because the server truncates rather than
raising.** A truncated answer to *"how many recalled precursors went undispositioned?"* is
not a smaller answer — it is a **wrong** one, and it looks exactly like a right one. So the
nine `mainline_audit` views are shaped aggregate-first to ≤`25` rows and measured at
≤`8192` bytes — `80 %` of the cap, deliberately, so that corpus growth breaches the budget
in CI
rather than in front of a judge.
`packages/mainline-mcp/src/mainline_mcp/budget.py` is the prober that measures actual
response bytes per view and records the worst observed row.

The nine views, and the question each answers, are tabulated in
[`VERIFY.md`](../VERIFY.md) Tier 3. Two of them carry `ancestry_complete`; when it is false
the counts beneath are **lower bounds** and the view says so rather than rounding the
problem away.

### The negatives are the interesting half

`mainline_qa`, `crdb_internal`, `pg_catalog`, `information_schema` and `pg_extension` must
all be **unreachable**
(`packages/mainline-mcp/src/mainline_mcp/limits.py:75` and `:89`), and `insert_rows` must be
rejected on every table except `mainline_meas.external_attestation`
(`packages/mainline-mcp/src/mainline_mcp/limits.py:101`) — a binding in the type, not a
runtime check. `tests/integration/mcp/test_negative_reachability.py` asserts these over the
live endpoint deliberately **bypassing our own client-side screen**, because a control that
lives only in our client is a control an attacker skips by not using our client.

The single permitted write exists so a third party's agent can record the outcome of *its
own* verification into our log — their claim about our log, never our claim about the
world. Insert-only is an exact match for append-only archival memory, which is why it is
the only write surface there is.

### The pessimistic assumption we published instead of guessing

Which SQL identity `select_query` runs as is undocumented. Rather than assume favourably,
`VERIFY.md` states that the MCP identity is treated as **admin-equivalent** and RLS is
assumed **not** to apply: every view on the surface is safe to read in full, `mainline_qa`
never receives an account on any tier, and MCP is never marketed as site-scoped.

---

## Tool 4 · CockroachDB Agent Skills — DESIGNED

Two authored skills plus one staged upstream contribution;
10 [src: evidence/tool-usage/crdb-features.json#rows.crdb_agent_skills.file_count] files
name them.

| skill | what it teaches | its executable assertion |
|---|---|---|
| `skills/designing-diachronic-gates/` | the PROJECT / PIN / REFUSE idiom — a trigger projecting a cross-row fact onto a scalar, a composite FK under `ON UPDATE RESTRICT` pinning a completed transition to an epoch, and a plain CHECK over that scalar | `skills/designing-diachronic-gates/scripts/assert_gate_refuses.py:57` — spins a throwaway node, replays an illegal history, and **fails unless the expected SQLSTATE and constraint name are raised** |
| `skills/designing-vector-recall-prefixes/` | C-SPANN prefix rules: one vector index per table, inline at create, every prefix column a single value, and the hint | `skills/designing-vector-recall-prefixes/scripts/assert_prefix_index_used.py` — **fails unless the plan actually chooses the index** |
| `skills/upstream/cockroachdb-resilience-and-disaster-recovery/verifying-a-restore-by-merkle-root/` | de-branded, staged for contribution back to Cockroach Labs | `skills/upstream/cockroachdb-resilience-and-disaster-recovery/verifying-a-restore-by-merkle-root/scripts/verify_restore_merkle_root.py` |

**Verdict: DESIGNED** — the skills and their scripts are on disk, and no run of either
script is captured under `evidence/`, so they are shipped and not yet evidenced.

The design point is the third column. A skill whose advice cannot be falsified is a blog
post; each of these ships a program that goes red when the guarantee stops holding. Both
also encode a *recovery* step most guidance omits: `P0001` carries no
`diag.constraint_name`, so the raising object has to be recovered from the message text,
and `skills/designing-diachronic-gates/scripts/assert_gate_refuses.py:57` is the regex that does it.

---

# Part 2 · AWS — twelve services

Account `0229…8246` (masked deliberately; not a credential, but an account number enables
cross-account enumeration and there is no reason to publish one). Profile `mainline-dev`,
region **`ap-southeast-2`** for Bedrock and **`ap-southeast-1`** for the demo stack beside
the database.

| service | verdict | files | anchor |
|---|---|---|---|
| Bedrock — Claude inference | DESIGNED | 245 [src: evidence/tool-usage/aws-services.json#rows.aws_bedrock_runtime.file_count] | `packages/mainline-agentkit/src/mainline_agentkit/transport.py:273` |
| Bedrock — embeddings | DESIGNED | 25 [src: evidence/tool-usage/aws-services.json#rows.aws_bedrock_embeddings.file_count] | `verticals/mainline/packages/mainline-recall-agent/src/mainline_recall_agent/providers/bedrock_titan.py:39` |
| **Bedrock Rerank** | **NOT-AVAILABLE** | 18 [src: evidence/tool-usage/aws-services.json#rows.aws_bedrock_rerank.file_count] | `docs/HONESTY.md:276` |
| S3 + Object Lock | DESIGNED | 117 [src: evidence/tool-usage/aws-services.json#rows.aws_s3_object_lock.file_count] | `infra/modules/evidence-store/main.tf:100` |
| KMS | DESIGNED | 41 [src: evidence/tool-usage/aws-services.json#rows.aws_kms.file_count] | `packages/trappoint-ledger/src/trappoint_ledger/signer.py:63` |
| CloudTrail | DESIGNED | 27 [src: evidence/tool-usage/aws-services.json#rows.aws_cloudtrail.file_count] | `infra/envs/evidence/main.tf:114` |
| Lambda | DESIGNED | 8 [src: evidence/tool-usage/aws-services.json#rows.aws_lambda.file_count] | `infra/modules/demo-api/main.tf:257` |
| CloudFront + OAC | DESIGNED | 32 [src: evidence/tool-usage/aws-services.json#rows.aws_cloudfront.file_count] | `infra/modules/demo-site/main.tf:263` |
| CloudWatch | DESIGNED | 21 [src: evidence/tool-usage/aws-services.json#rows.aws_cloudwatch.file_count] | `infra/modules/demo-api/main.tf:391` |
| IAM | DESIGNED | 16 [src: evidence/tool-usage/aws-services.json#rows.aws_iam.file_count] | `infra/modules/evidence-store/main.tf:145` |
| SSM Parameter Store | DESIGNED | 8 [src: evidence/tool-usage/aws-services.json#rows.aws_ssm_parameter_store.file_count] | `infra/modules/demo-api/main.tf:146` |
| EventBridge | DESIGNED | 24 [src: evidence/tool-usage/aws-services.json#rows.aws_eventbridge.file_count] | `verticals/mainline/apps/steward/schedules.yaml:14` |

## Amazon Bedrock — inference

**Live in the account.** Region `ap-southeast-2` (Sydney) carries `8` `au.*` Claude
inference profiles — including `au.anthropic.claude-opus-5` and
`au.anthropic.claude-sonnet-5` — plus `amazon.titan-embed-text-v2:0` and
`cohere.embed-v4:0`. That enumeration is recorded at
`docs/adr/0002-g1-platform-ground-truth.md:65` from a live `ListInferenceProfiles` call;
**this document did not re-verify it**, because doing so needs the credential a reader of
this document does not have.

**How.** `bedrock-runtime` `InvokeModel` with the Anthropic native body. The `modelId` is
an `au.*` inference-profile ARN **resolved at start-up** from `ListInferenceProfiles` and
pinned into the run record — never hard-coded, so that if a Claude generation ships without
an `au.*` profile the system fails loudly instead of silently reaching another region.
`packages/mainline-agentkit/src/mainline_agentkit/transport.py:273` refuses any identifier
lacking the `au.` prefix as a residency violation, and
`tests/unit/recall_providers/test_no_hardcoded_model_ids.py` fails the build on a
hard-coded model id anywhere.

One model generation across the whole fleet, differentiated by **effort** rather than by
model — low for triage and extraction, high for adjudication, xhigh for listwise reranking.
One model id means one profile ARN in the endpoint policy means one `403` path instead of
two.

**Verdict: DESIGNED, not EXERCISED, and this is the honest half.** Every agent test in this
repository replays a **recorded cassette**. A green agent test proves the code handles that
recorded exchange; it proves nothing about a live model's behaviour today. Where a live
call is genuinely required, the test skips with a reason and the reason is in the census.
No live-inference transcript is committed under `evidence/`. See
[`docs/HONESTY.md`](HONESTY.md) § SYNTHETIC.

## Amazon Bedrock — embeddings

`amazon.titan-embed-text-v2:0` at
`verticals/mainline/packages/mainline-recall-agent/src/mainline_recall_agent/providers/bedrock_titan.py:39`,
with `cohere.embed-v4:0` as the second available model. Embeddings are written into the
C-SPANN sidecar tables described above, and **every embedding row stores its `embed_model`
and `index_gen`** — `verticals/mainline/db/migrations/0031_clause_embedding.sql` carries
`CONSTRAINT embed_model_stated` and `CONSTRAINT index_gen_stated` — because a vector whose
model is unknown cannot honestly be compared with anything.

**Verdict: DESIGNED.** The committed embeddings are fixtures, which is exactly why Tier-2
verification in `VERIFY.md` — clone, `just up`, `just migrate`, `just conform` — needs **no
model call and no cloud account at all**. The refusal reproduces on a stranger's laptop.

## Amazon Bedrock Rerank — NOT-AVAILABLE

**Not offered in `ap-southeast-2`, and no dependency was taken on it**
(`docs/HONESTY.md:276`). It is listed here rather than omitted because a services list that
silently drops what you checked for and could not have is a list nobody can audit. Listwise
reranking is done by the Claude profile at high effort; on the retrieval side CockroachDB's
own `vector_search_rerank_multiplier` session variable (observed at `50`, with
`vector_search_beam_size` at `32`) governs ANN candidate expansion. The design assumed
Rerank's absence *before* it was checked, and the check agreed.

## S3 + Object Lock — the evidence store

`infra/modules/evidence-store/main.tf` — `aws_s3_bucket:74`, `versioning:89`,
`object_lock_configuration:100`, `public_access_block:113`, `bucket_policy:335`.

**How.** Checkpoints of the tamper-evident ledger are appended to a versioned bucket in
**COMPLIANCE** mode, which even the root account cannot shorten. `object_lock_enabled` is
set **at bucket creation** because it cannot be added afterwards — the module treats that as
a one-shot and refuses a plan that would create a second bucket. The writer identity is
denied `s3:DeleteObjectVersion` and denied `PutObjectRetention` with an unconstrained
retention date, so the identity that appends checkpoints cannot shorten or remove them.

`infra/policy/custody/object_lock.rego` and `infra/policy/custody/kms_custody.rego` assert
each of those denials against `plan_compliant.json` and a family of deliberately broken
plans under `infra/policy/custody/fixtures/`, each named for the control it removes:
`ol1_no_object_lock`, `ol2_versioning_suspended`, `ol3_governance_one_year`,
`ol4_public_policy_allowed`, `ol5_sse_kms`, `kms1_destruction_ungated`,
`kms2_rotation_enabled`, `kms3_seven_day_window`, `kms4_symmetric_key`,
`iam1_writer_can_delete`, `iam2_unconstrained_retention`, `gt18_two_buckets`,
`destroy1_key_deleted`, `plan1_unresolved_policy`. A policy suite that has only ever seen a
passing plan asserts nothing.

**Verdict: DESIGNED, and this is the sharpest limitation in this document.** No bucket has
been applied. From `docs/HONESTY.md`: *the AWS evidence store is described, not exercised
under load* — the bundle's archive section carries object-lock modes and retention dates,
and **the check that would compare them against live object versions is one of the seven
cryptographic checks that did not run**
[src: qa/test-state.json#external_checks.custody_bundle_verification.counts.not_checked].
The offline custody verification exits `2`
[src: qa/test-state.json#external_checks.custody_bundle_verification.exit_code] precisely
so that nobody reads its nine passes
[src: qa/test-state.json#external_checks.custody_bundle_verification.counts.passed] as a
verified ledger.

## AWS KMS — the checkpoint signing key

`packages/trappoint-ledger/src/trappoint_ledger/signer.py:63` and the key resources at
`infra/modules/evidence-store/main.tf:477` / `:501`.

**How, and why each choice is a choice.** `ECC_NIST_P256`, `SIGN_VERIFY`,
`ECDSA_SHA_256`, and **`MessageType = RAW`** — KMS hashes the message itself. Passing our
note text under `DIGEST` would have KMS hash it a *second* time and produce a valid
signature over the wrong thing, which is precisely the failure KMS exists to prevent, so
the constant names itself loudly at
`packages/trappoint-ledger/src/trappoint_ledger/signer.py:69`. DER signatures are stored
**exactly as KMS returns them**, with no re-encoding to fixed-width `r‖s`, because the offline verifier
calls Go's `ecdsa.VerifyASN1` and the two must agree byte for byte. Rotation is **off** —
a rotated signing key silently invalidates historical verification — and key deletion is
gated, with `boto3` imported inside the adapter rather than at module scope so the whole
package stays importable, and testable, on a machine with no AWS at all.

The threat model is explicit at
`packages/trappoint-ledger/src/trappoint_ledger/signer.py:196`: a T1 adversary holding
arbitrary SQL has no path to `kms:Sign`.

**Verdict: DESIGNED.** Unit-tested against an injected client; the live signature check is
another of the seven that did not run.

## AWS CloudTrail — custody of the custodian

`infra/envs/evidence/main.tf:114`, multi-region, with `enable_log_file_validation`.

**How.** Log-file validation makes AWS produce **its own signed digest chain** over the
same events — weaker than ours, because AWS holds the key, and valuable for exactly that
reason: **it is a chain we could not have forged.** Two advanced event selectors: management
events, so `kms:ScheduleKeyDeletion`, `PutKeyPolicy`, `PutBucketPolicy` and
`PutObjectLockConfiguration` become visible to the custody patrol within one checkpoint
cadence instead of at the next audit; and data events on the checkpoint bucket, which are
expensive on a busy bucket and trivial on this one at `1440` objects a day.

**Verdict: DESIGNED.** No trail exists in the account. Note the interaction with the
`ccloud` limitation above: the *control-plane* half of "custody of the custodian" has no
input source on the Basic tier regardless of CloudTrail, because the Cloud audit-log
endpoints `404`.

## AWS Lambda, CloudFront + OAC, CloudWatch, IAM, SSM Parameter Store — the demo stack

```
judge's browser ──► CloudFront ──/v1/*──► Lambda Function URL (AWS_IAM, OAC-signed)
                                                 │ pgwire, TLS, same region
                                                 ▼
                        CockroachDB Cloud Basic · mainline-dev · Singapore
```

* **Lambda** — one `python3.13` function (`infra/modules/demo-api/main.tf:192`) behind a
  Function URL whose `authorization_type` is **`AWS_IAM`**, never `NONE`
  (`infra/modules/demo-api/main.tf:257`–`:262`). It runs in `ap-southeast-1` beside the
  cluster because the same call from `ap-southeast-2` pays roughly `90 ms` each way and the
  gate screen makes six of them — about `1.1 s` of pure geography on the one page judges
  look at.
* **CloudFront + Origin Access Control** — one distribution
  (`infra/modules/demo-site/main.tf:263`) fronts both the private S3 origin holding the
  static console and the Lambda Function URL, so the judge sees one origin and the bucket
  is never public. OAC (not the legacy OAI) signs both origins, which is what lets the
  Function URL keep `AWS_IAM` instead of `NONE`.
* **CloudWatch** — a log group with **finite** retention
  (`infra/modules/demo-api/main.tf:105`), four metric alarms, and one dashboard
  (`infra/modules/demo-api/main.tf:391`). Unbounded retention on a demo account is a cost
  bug, not a safety feature.
* **IAM** — the interesting IAM here is what is **denied**:
  `infra/modules/evidence-store/main.tf:145` is the policy document that denies the
  checkpoint writer `s3:DeleteObjectVersion` and denies `PutObjectRetention` without a
  bounded retention date. The Lambda execution role's entire non-managed grant is
  `ssm:GetParameter` on one parameter plus a conditioned `kms:Decrypt`.
* **SSM Parameter Store** — the CockroachDB Cloud DSN is a SecureString parameter
  (`infra/modules/demo-api/main.tf:146`), **not** a Lambda environment variable, so the
  connection string never appears in the function configuration that anyone holding
  `lambda:GetFunction` can read.

**Verdict on all five: DESIGNED.** Nothing is deployed; the submission's demo URL is
unresolved as of this document. `docs/submission/SUBMISSION.json` is the single place a
resolved URL is written.

## Amazon EventBridge — DESIGNED, and weaker than the others

`verticals/mainline/apps/steward/schedules.yaml:14` describes scheduled invocations keyed
by `(schedule_id, occurrence_ts)`, where `occurrence_ts` is EventBridge's
`<aws.scheduler.scheduled-time>` — the same value on every retry of one occurrence, which
is what makes a run idempotent. The schedule is external by necessity: CockroachDB's
`CREATE SCHEDULE` exists only for backups and changefeeds, so no part of this system may
assume in-database cron.

**Stated plainly: there is no `aws_cloudwatch_event_*` or scheduler resource anywhere under
`infra/`.** Today the schedule lives in that YAML file and a container entrypoint. This row
is DESIGNED in the weakest sense of the word, and it is listed because leaving it out of a
services document while the runbooks name it would be the wrong kind of tidy.

---

# Part 3 · Where this actually runs, and what that costs

| layer | where |
|---|---|
| Database | CockroachDB v26.2.5 Basic, **`aws-ap-southeast-1` — Singapore** |
| Demo stack (designed) | Lambda + CloudFront, **`ap-southeast-1` — Singapore** |
| Inference | Amazon Bedrock, **`ap-southeast-2` — Sydney** |

Sydney is Advanced-tier only for CockroachDB Cloud, so it is absent from the Basic region
list. **Any claim of end-to-end Australian data residency is false for this deployment**,
and the split is stated here, in `VERIFY.md`, and in the README, and is nowhere rounded
off.

**Cost.** The cluster carries a configured `spend_limit` of `2500` (`US$25.00`/month) — a
ceiling, not a spend — against free-tier allowances of `100M` request units and `10 GiB`,
all three quoted from the captured transcript above. The cheapest deployment satisfying
*"functional demo URL, free and unrestricted for judges"* is a static console build with
committed replay fixtures, which needs no server, no credential
and no egress, at **`US$0`/month**, against roughly `US$5–8`/month for the cheapest
always-on container.

---

# Part 4 · What is NOT claimed

Collected here so a judge does not have to hunt for it. Every line is also in
[`docs/HONESTY.md`](HONESTY.md).

* **Bedrock Rerank is unavailable in `ap-southeast-2`.** No dependency was taken.
* **`ccloud` `0.6.12` cannot authenticate headlessly.** Agent paths use the Cloud REST API.
* **Cloud audit-log endpoints `404` on Basic.** "Custody of the custodian" has no
  control-plane input source on this tier.
* **The S3 object-lock check did not run** — one of the
  7 [src: qa/test-state.json#external_checks.custody_bundle_verification.counts.not_checked]
  cryptographic checks registered, named, and reported as *not checked* rather than passed.
* **No live Bedrock inference transcript is committed.** Agent tests replay cassettes.
* **Nothing has ever run against CockroachDB Cloud in CI.** The nightly truth check is
  designed, not scheduled.
* **No live MCP session against the managed endpoint is captured.** The suites skip with a
  reason rather than pass empty.
* **The conformance suite has never been demonstrated.** Against a bare node its cases
  *error* rather than skip; `just migrate && just conform` is the invocation that would run
  them. This is the single largest gap between what the repository contains and what it has
  shown.
* **Nothing is deployed.** Every AWS row in Part 2 except the model access is DESIGNED, and
  the submission's demo URL is `UNRESOLVED` in `docs/submission/SUBMISSION.json` as this
  document is written.

---

# Part 5 · Re-deriving every number here

```bash
# the two censuses this document cites for every file count
python scripts/submission/capture_tool_evidence.py            # write
python scripts/submission/capture_tool_evidence.py --check    # exit 1 if stale

# the node every "Measured on the pinned local node" block ran against
just up     # cockroachdb/cockroach:v26.2.5, single node, insecure
#   DSN: postgresql://root@localhost:26257/defaultdb?sslmode=disable

# the refusal this document calls the product
python scripts/proof/gate_refusal.py --dsn postgresql://root@localhost:26257/defaultdb?sslmode=disable

# the test and check census the honesty numbers come from
python scripts/qa/report_test_state.py
```

Reference format: `[src: path#json.path.to.value]`, resolved against
`evidence/tool-usage/*.json`, `evidence/gate-refusal/*.json` and `qa/test-state.json`. A
number in this document with no reference beside it is a defect; report it.

Related reading: [`VERIFY.md`](../VERIFY.md) — three ways to check the claim without
trusting us. [`docs/HONESTY.md`](HONESTY.md) — everything this build gets wrong, counted.
[`evidence/tool-usage/README.md`](../evidence/tool-usage/README.md) — how the censuses are
built and why they carry no timestamp.
