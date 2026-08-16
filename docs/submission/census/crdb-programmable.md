<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# CENSUS — CockroachDB as a programmable, self-defending database

**Worker:** W6 · **Date:** 2026-08-16 · **Lead plan:** `docs/submission/feature-census-plan.md`
**Cluster measured:** local CockroachDB CCL v26.2.5, database `mainline_demo`
**Live origin corroborated:** `https://ihuuyvm4z6nfuktihnkey77fpy0eyrhj.lambda-url.ap-southeast-1.on.aws`

This file covers the **procedural and security half** of the database: the routines, the
triggers, row-level security, the role lattice, recursive CTEs, and one guarded `RETURNING`.
It is the material behind judging axis one, because it is the half that decides what the
memory layer will **refuse**.

The argument in one line, and every row below is evidence for it:

> **The refusal logic is inside the database, not in front of it.** An agent that holds the
> demo's credential, and an agent that has corrupted the memory's own cached counter, both
> still fail to write. The check is not a service the agent calls; it is a property of the
> relation the agent writes to.

---

## 0. HOW EVERY NUMBER ON THIS PAGE WAS PRODUCED

**One probe carries the ten headline counts.** It ran today, 2026-08-16, against a local
CockroachDB CCL v26.2.5 holding `mainline_demo` built from the same 271-file chain the live
origin reports; its output is pasted verbatim and unedited. Two independent cross-checks follow
it — one that needs no cluster at all, and one test run reported from `--junitxml`. Individual
rows below add their own pasted transcripts where a row claims something the count cannot show
(a refusal firing, a platform limitation, an HTTP response). Everything else on this page is a
path, a line number, or a quotation.

Set the shorthand once (the container is the repo's local cluster, already running):

```bash
CRDB='docker exec trappoint-crdb ./cockroach sql --url postgresql://root@localhost:26257/mainline_demo?sslmode=disable --format=table -e'
```

```sql
SELECT 'plpgsql functions' AS what, count(*) AS n FROM pg_proc p JOIN pg_language l ON l.oid=p.prolang JOIN pg_namespace n ON n.oid=p.pronamespace WHERE l.lanname='plpgsql' AND p.prokind='f' AND n.nspname NOT IN ('pg_catalog','information_schema','crdb_internal')
UNION ALL SELECT 'plpgsql procedures', count(*) FROM pg_proc p JOIN pg_language l ON l.oid=p.prolang JOIN pg_namespace n ON n.oid=p.pronamespace WHERE l.lanname='plpgsql' AND p.prokind='p' AND n.nspname NOT IN ('pg_catalog','information_schema','crdb_internal')
UNION ALL SELECT 'trigger objects (pg_trigger)', count(*) FROM pg_trigger WHERE NOT tgisinternal
UNION ALL SELECT 'trigger-event pairs (info_schema)', count(*) FROM information_schema.triggers
UNION ALL SELECT 'tables relrowsecurity', count(*) FROM pg_class WHERE relrowsecurity
UNION ALL SELECT 'tables relforcerowsecurity', count(*) FROM pg_class WHERE relforcerowsecurity
UNION ALL SELECT 'rls policies', count(*) FROM pg_policies
UNION ALL SELECT 'restrictive policies', count(*) FROM pg_policies WHERE permissive='restrictive'
UNION ALL SELECT 'triggers bound to fn_refuse_mutation', count(*) FROM pg_trigger t JOIN pg_proc p ON p.oid=t.tgfoid WHERE NOT t.tgisinternal AND p.proname='fn_refuse_mutation'
UNION ALL SELECT 'SECURITY DEFINER routines', count(*) FROM pg_proc p JOIN pg_language l ON l.oid=p.prolang JOIN pg_namespace n ON n.oid=p.pronamespace WHERE l.lanname='plpgsql' AND p.prosecdef AND n.nspname NOT IN ('pg_catalog','information_schema','crdb_internal');
```

**Output, 2026-08-16, pasted unedited:**

```
                  what                 | n
---------------------------------------+-----
  plpgsql functions                    | 26
  plpgsql procedures                   |  2
  trigger objects (pg_trigger)         | 39
  trigger-event pairs (info_schema)    | 59
  tables relrowsecurity                |  4
  tables relforcerowsecurity           |  4
  rls policies                         | 25
  restrictive policies                 |  5
  triggers bound to fn_refuse_mutation | 17
  SECURITY DEFINER routines            |  0
(10 rows)
```

**A second check that needs no cluster at all, and a stranger with only a clone can run it.**
The procedural layer is rendered one object per file, so the file counts and the catalog counts
must agree. They do:

```bash
cd verticals/mainline/db/migrations
ls | grep -c _fn_      # 26   ==  plpgsql functions
ls | grep -c _proc_    #  2   ==  plpgsql procedures
ls | grep -c _trg_     # 39   ==  trigger objects
ls | grep -c _policy_  # 25   ==  rls policies   (0181b–h, 0183b–h, 0185b–h, 0187b–e)
ls | grep -cE "_rls_(enable|force)"   # 8 == 4 tables x (ENABLE + FORCE)
```

Four of those five numbers have an exact `pg_catalog` counterpart in the probe above — 26, 2,
39, 25 — produced from the filesystem and matching numbers produced from the cluster. (The
fifth, 8, is the `ENABLE`/`FORCE` pair count behind the 4/4 in the probe.) That agreement is
itself the claim that the deployed schema is the schema in the repository, and it costs a judge
five seconds and no infrastructure.

The corroborating suite run, today, `--junitxml` and not a terminal tail:

```
.venv/Scripts/python.exe -m pytest tests/integration/schema/test_mi_rls.py -q \
  -p no:randomly --junitxml=<scratch>/w6_rls_static.xml

<testsuite name="pytest" errors="0" failures="0" skipped="0" tests="60" time="89.224"
           timestamp="2026-08-16T21:03:37.543757+10:00" hostname="AetherX">
```

**60 tests, 0 failures, 0 errors, 0 skipped.** The `--junitxml` was written to this worker's
scratch directory, not into the repository — this workstream adds one Markdown file and nothing
else. Nothing here changed a test, a threshold or a ratchet; the baseline 1070 / 1069 / 0 / 0 is
untouched.

> **One measured side effect, recorded rather than glossed.** That suite is the schema tier: it
> writes into the local `mainline_demo` under **its own private `site_id`** (`conftest.py`'s
> `Site` fixture is the isolation primitive — a private site, not a private database). Row counts
> on the local cluster therefore moved during this worker's session — `mainline.permit` went from
> 2 rows to 4, on four distinct sites. **The demo subject did not move.** Measured after the run:
>
> ```
>                   site                 | permits
> ---------------------------------------+----------
>   1e58eca5-48c8-5697-a408-27051e59e67b |       1     <- test site
>   7a047814-c1ea-5a78-a30c-943ca779bce3 |       1     <- test site
>   a601b4e4-a7e6-5f4f-be3d-6746fba4a20a |       1     <- test site
>   dec0de00-0001-4000-8000-000000000001 |       1     <- the seeded demo site, unchanged
> ```
>
> The deployed cloud cluster was never connected to at the SQL layer, and the demo it serves is a
> different database on a different cluster.

---

## 1. THE CORRECTIONS THIS CENSUS MAKES — THREE TO ITS OWN BRIEF, THREE TO THE TREE

R8 of the lead plan established the discipline: an imprecise number gets corrected, and the
correction is usually *upward*. Three apply here. All three were caught by running the probe
rather than by trusting the brief.

### 1.1 "59 triggers" is two different numbers, and only one of them survives contact

`information_schema.triggers` emits **one row per (trigger, event)**: a trigger declared
`BEFORE UPDATE OR DELETE` produces two rows, and `BEFORE INSERT OR UPDATE OR DELETE` produces
three. `pg_trigger` counts trigger *objects*.

```
trigger objects (pg_trigger)       | 39
trigger-event pairs (info_schema)  | 59
```

Both are true and they measure different things. **The number to say is 39 trigger objects
covering 59 (trigger, event) pairs.** A judge who runs the obvious `SELECT count(*) FROM
pg_trigger` gets 39; if the submission has said "59 triggers" flat, we have handed them an
apparent inflation to find in one query. Saying both numbers costs one clause and converts
that trap into a demonstration of precision.

### 1.2 "ten tables refuse mutation outright" understates it by seven

The brief describes eleven `trg_refuse_mutation_*` files (`0128` through `0128j`) making "ten
tables refuse mutation". The file count is eleven and it covers **eleven** tables, not ten — the
`0128` header itself says *"Weld 1 of 11"* and lists them. And the family does not stop there:
measured, `fn_refuse_mutation` is welded to **17 tables**, because six further `_trg_` files in
the `0145`/`0149` bands bind the same function to the custody and measurement relations.

```sql
SELECT p.proname, count(DISTINCT t.tgrelid) AS tables_welded
  FROM pg_trigger t JOIN pg_proc p ON p.oid=t.tgfoid
 WHERE NOT t.tgisinternal AND p.proname='fn_refuse_mutation' GROUP BY 1;

         guard        | tables_welded
----------------------+----------------
  fn_refuse_mutation  |            17
```

The seventeen: `blocking_check`, `cbm_account`, `clause_blame_closure`, `clause_version`,
`cr_event`, `exposure_line`, `exposure_receipt`, `identity_assignment`, `merge_record`,
`override_ledger`, `permit_event`, `person`, `signing_credential` (all `mainline`), plus
`agent_action`, `mutation_result`, `mutation_run`, `person_measure_policy` (`mainline_meas`).

Eleven of those come from `0128`–`0128j`; the other six from `0145e_trg_cbm_account_append_only`,
`0145f_trg_identity_assignment_append_only`, `0149a_trg_agent_action_append_only`,
`0149b_trg_person_measure_policy_append_only`, `0149y_trg_mutation_run_append_only` and
`0149z_trg_mutation_result_append_only`. An eighteenth table, `mainline.refusal_ledger`, is
append-only under a *different* and stricter guard — row R7.

### 1.3 `0034_event_edge.sql` contains no executable recursive CTE

The brief lists `verticals/mainline/db/migrations/0034_event_edge.sql` as a recursive-CTE
site. It is not one. The `WITH RECURSIVE` at `0034_event_edge.sql:42` sits inside a `--`
comment block, quoting the closure writer in order to justify the `no_self_edge` CHECK
constraint that file actually creates.

```bash
grep -vE "^\s*--" verticals/mainline/db/migrations/0034_event_edge.sql | grep -c RECURSIVE
# 0
```

The executable recursive CTEs are elsewhere and there are more of them than the brief named —
see row R11. This correction *removes* a claim; it is here because a judge who greps `0034`
for a live CTE and finds a comment will discount the rows that were right.

### 1.4 Three further corrections, to the tree rather than to the brief

Found while checking the rows below, recorded where the row that found them sits, and collected
here so nothing depends on a reader noticing them in passing. None is a defect in the database;
all three are pointers in prose that no longer resolve, and each would cost more to be caught by
a judge than to be stated by us.

| # | where | what is stale | corrected in |
|---|---|---|---|
| a | `cf22_gate_under_force_rls.py:22-24` | says the RLS policy-drop half is registered in the unwelding suite and carried by `REFUSAL_DEPTH.md`. Measured: 0 hits in either. The capability is real; it lives in `test_mi_rls.py`. | R8 |
| b | `GRANTS.yaml:646,649` | the `census_note` cites `transitions.py:891` / `:969`; today the statements are at `:925` / `:1003` | §3 |
| c | `refusal.py` docstring | names `tests/test_refusal_row_factory.py`, which is app-relative; the repo-root path is `verticals/mainline/apps/demo-api/tests/test_refusal_row_factory.py` | R12 |

**No file outside this one was edited to fix them.** They are the orchestrator's to take or leave.

---

## 2. THE ROWS

Row shape is the lead plan's §4 shape. States are the plan's R2 vocabulary: **LIVE** (in this
demo's request path), **REPO** (exercised in the repository, not in that path), **APPLIED**,
**DECLARED**, **NOT-AVAILABLE**.

A note on how LIVE is established for this domain, stated once, because it is the join between
a catalog probe on a local cluster and a claim about a deployed one.

**Step 1 — same chain.** `GET /v1/health` on the live origin returns, today:

```json
{"ok": true, "database": "mainline_demo",
 "cluster_version": "CockroachDB CCL v26.2.5 (x86_64-pc-linux-gnu, built 2026/07/28 …)",
 "deploy_chain_applied": 271, "deploy_chain_files": 271, "migrations_applied": 0,
 "schema_fingerprint": "ec9b1ce70a8df066e5763056c5ad9376800ef5df9362f7d0502b1dc7e7450339"}
```

`ls verticals/mainline/db/migrations/*.sql | wc -l` returns **271**, and
`evidence/deploy/cloud-chain.json` records that this exact tree was applied to
`mainline-dev-31219.j77.aws-ap-southeast-1.cockroachlabs.cloud … /mainline_demo` with
`files 271 / applied 271 / failed 0`, verdict `APPLIED`. The local cluster reports the same
shape — 271 files on disk, `trappoint.schema_migration` empty because the deploy chain applies
directly, which is exactly what `migrations_applied: 0` says on the live side. Every migration
cited below is a member of that chain.

**Step 2 — fired, not merely present.** Where a row claims the object *ran on the live origin*,
it cites one of two transcripts. `evidence/demo/live-beats.json` is committed
(`generated_at 2026-08-15T14:11:35Z`, `credentials_used: "none — no DSN, no AWS profile, no
token; a stranger with the URL"`, `target_is_local_emulator: false`, `verdict: PROVEN`). And it
was **re-run today**, by this worker, with the one command a judge would use:

```bash
curl -s -X POST https://ihuuyvm4z6nfuktihnkey77fpy0eyrhj.lambda-url.ap-southeast-1.on.aws/v1/demo/gate-run \
  -H 'content-type: application/json' -d '{}'
# HTTP 200, 10499 bytes
# data.verdict            = PROVEN
# data.run_id             = 11c8422e-53a1-481d-92fc-b949bd85da4b
# data.generated_at       = 2026-08-16T10:58:07Z
# data.transaction.isolation  = SERIALIZABLE
# data.transaction.disposition = rolled_back
# data.persistence_check.identical = true
```

The envelope names the database objects it ran, in a field built for exactly this question:

```json
"statement_refs": [
  {"kind": "procedure", "object": "mainline.merge_permit"},
  {"kind": "procedure", "object": "trappoint.explain_refusal"},
  {"kind": "table", "object": "mainline.permit"},
  {"kind": "table", "object": "mainline.disposition"},
  {"kind": "table", "object": "mainline.merge_record"}
]
```

A PL/pgSQL **procedure** and a PL/pgSQL **function**, named by the live origin itself, in a
response a stranger can fetch with no credential. That is the LIVE evidence for rows R1, R2, R3
and R6, and it is one request.

**No credential was used and the cloud cluster was never connected to at the SQL layer.** Every
`pg_catalog` number on this page comes from the local v26.2.5 cluster running the same 271-file
chain; every "it fired" claim comes from the public HTTP surface.

---

### R1 · PL/pgSQL stored functions

```
state:         LIVE
what it is:    26 PL/pgSQL functions carrying the projection, chain, gate and refusal logic
               inside the database engine.
where:         verticals/mainline/db/migrations/0100–0119b — the binding actually deployed;
               26 files, `ls | grep -c _fn_` = 26, one CREATE FUNCTION each. 25 land in schema
               `mainline`, one (`0119a`) in the shared `trappoint` schema.
               The reference binding renders 14 of the same functions at
               packages/trappoint-sql/refvertical/sql/0100–0119b — fewer, because the mainline
               binding adds twelve the reference does not declare: the recall family (0110,
               0112, 0113), the cue-projection family (0114, 0114a), the CBM/identity family
               (0140–0140d, 0141) and the ledger compare-and-swap (0119). 14 + 12 = 26.
verify in 60s: $CRDB "SELECT count(*) FROM pg_proc p JOIN pg_language l ON l.oid=p.prolang
               JOIN pg_namespace n ON n.oid=p.pronamespace WHERE l.lanname='plpgsql'
               AND p.prokind='f' AND n.nspname NOT IN
               ('pg_catalog','information_schema','crdb_internal');"
               → first line of the result body: `26`
say this:      "Twenty-six PL/pgSQL functions run inside CockroachDB. The gate is not a service
               the agent calls before writing; it is a property of the write."
never say:     "The application validates the write." It does not, and the whole point is that
               it cannot be made to skip the validation.
```

Twenty-five are in schema `mainline`; one, `trappoint.explain_refusal`, is in the shared
`trappoint` schema. Twenty-three of the twenty-six are bound to at least one trigger. The
three that are not are called directly: `fn_site_role` (projects the RLS scope token),
`fn_ledger_cas_append` (compare-and-swap into the custody ledger), and
`trappoint.explain_refusal` (row R6).

**`SECURITY DEFINER` count is zero, and that is a deliberate, load-bearing design decision,
not an omission.** Every trigger executes as the *invoking* role, so a trigger that writes an
RLS-forced table needs an explicit write policy of its own, and cannot be used as a privilege
escalation ladder. `verticals/mainline/db/RLS-MATRIX.yaml` records the coupling openly rather
than hiding it, and `tests/integration/schema/test_mi_rls.py::test_no_trigger_function_is_security_definer`
is the ratchet that keeps it at zero.

---

### R2 · PL/pgSQL stored procedures

```
state:         LIVE
what it is:    2 PL/pgSQL PROCEDUREs — the transactional merge entry points, invoked by CALL.
where:         verticals/mainline/db/migrations/0117_proc_merge_permit.sql ·
               0118_proc_merge_change_request.sql (mirrored in the reference binding at
               packages/trappoint-sql/refvertical/sql/) · deployed as mainline.merge_permit and
               mainline.merge_change_request
               called at verticals/mainline/apps/demo-api/src/mainline_demo_api/gate_run.py:169
               `_MERGE_SQL: Final = "CALL mainline.merge_permit(%s, %s, %s, %s, %s, %s, %s, %s)"`
verify in 60s: $CRDB "SELECT n.nspname||'.'||p.proname FROM pg_proc p JOIN pg_language l
               ON l.oid=p.prolang JOIN pg_namespace n ON n.oid=p.pronamespace
               WHERE l.lanname='plpgsql' AND p.prokind='p';"
               → `mainline.merge_change_request` and `mainline.merge_permit`
say this:      "The demo's merge beat is a CALL of a stored procedure. The transaction boundary
               and the gate live on the same side of the wire."
never say:     "Stored procedures are used for convenience." They are the transaction boundary;
               that is why the gate cannot be bypassed by reordering client statements.
```

The `CALL` appears in the live transcript. `evidence/demo/cr-gate/raw/gate_run.json` records
`"statement":"CALL mainline.merge_permit(%s, %s, %s, %s, %s, %s, %s, %s)"`, and the live
response fetched today carries the same string on beat 2 plus, on beat 3, the attack form that
shows the procedure is the *only* way in:

```
beat 2 statement: CALL mainline.merge_permit(%s, %s, %s, %s, %s, %s, %s, %s)
beat 3 statement: UPDATE mainline.permit SET open_blocking = 0 WHERE permit_id = %s;
                  CALL mainline.merge_permit(%s, %s, %s, %s, %s, %s, %s, %s)
```

PL/pgSQL procedures — as distinct from functions — are a comparatively recent CockroachDB
capability, and this project uses them for the one thing they are uniquely good at: owning a
multi-statement transaction that a client cannot take apart. `merge_permit` does eight things in
one call — read the head, re-derive the clearance, append the chained transition event, pin the
gate epoch through a composite FK under `ON UPDATE RESTRICT`, write the custody-ledger intake,
and compare-and-swap the head — and a client that wanted to skip one of them has no seam to do
it at, because the only exposed verb is `CALL`.

---

### R3 · Triggers, and the families they form

```
state:         LIVE
what it is:    39 trigger objects covering 59 (trigger, event) pairs, all FOR EACH ROW,
               binding 23 of the 26 PL/pgSQL functions to the tables they defend.
where:         verticals/mainline/db/migrations/0120–0149z — one `CREATE TRIGGER` per file,
               39 files (`ls | grep -c _trg_` = 39) · the reference binding renders 22 trigger
               files of its own at packages/trappoint-sql/refvertical/sql/0120–0133, from the
               same Jinja templates — packages/trappoint-sql/templates/0120_triggers_projection.sql.j2
               and 0130_triggers_merge_gate.sql.j2
verify in 60s: $CRDB "SELECT count(*) FROM pg_trigger WHERE NOT tgisinternal;"   → `39`
               $CRDB "SELECT count(*) FROM information_schema.triggers;"          → `59`
               $CRDB "SELECT action_orientation, count(*) FROM information_schema.triggers
                      GROUP BY 1;"                                                → `ROW | 59`
say this:      "Thirty-nine row-level triggers over twenty-six PL/pgSQL functions. The memory
               layer's rules are welded to the tables, so every writer meets them — including
               one that never read our code."
never say:     "59 triggers." Say 39 objects / 59 trigger-event pairs. See §1.1.
```

Every one is `FOR EACH ROW` — measured, `action_orientation` is `ROW` on all 59 pairs, 54 `BEFORE`
and 5 `AFTER`. There is no statement-level trigger anywhere in the schema, which is what makes
"every writer meets them" true of every writer rather than of every *statement*.

The families, each named with its migration numbers, and what each one refuses. One row is not a
trigger family and is marked so — `0119a` is a callable function, listed here because it belongs
to the same refusal machinery and a reader looking for it will look in this table:

| family | migrations | what it refuses |
|---|---|---|
| **check projection & materialisation** | `0100`, `0101`, `0120`, `0121` | a `blocking_check` row whose projection does not agree with the counter it feeds; the row is materialised and a plain-column CHECK then refuses over the counter |
| **disposition project / close / retract-only** | `0102`–`0104`, `0122`–`0124` | any edit to a disposition other than retraction — a disposition is superseded, never rewritten |
| **hash-chain enforcement** | `0105`, `0106`, `0125`, `0126` | an event whose `prev_digest` does not equal its predecessor's `chain_digest` (row R5) |
| **closure guard** | `0108`, `0127` | a blame-closure generation that is not internally consistent with the DAG it claims to summarise |
| **merge gates** | `0115`, `0116`, `0130`, `0131` | a merge of a subject carrying an undischarged obligation — the headline refusal (below) |
| refusal explanation *(function, no trigger)* | `0119a` | a refusal with no exhibit, and a decomposition it cannot justify (row R6) |
| **refusal-ledger append-only guard** | `0119b`, `0133` | an `UPDATE`/`DELETE` on the refusal ledger, *and* an `INSERT` whose reason set is empty or outside a closed vocabulary (row R7) |
| **append-only weld** | `0128`–`0128j`, `0145e`–`0145f`, `0149a`–`0149z` | every `UPDATE` and `DELETE` on 17 evidentiary tables (row R4) |

**The merge gate firing on the live origin is the strongest single fact in this census.**
`evidence/demo/live-beats.json` (generated 2026-08-15T14:11:35Z, `verdict: PROVEN`) is one
HTTP request to `POST /v1/demo/gate-run` producing four beats under one AWS request id — and
the identical four beats came back from the same URL **today**, run `11c8422e`, `2026-08-16T10:58:07Z`:

| beat | outcome | SQLSTATE | exhibit | matched its declared expectation |
|---|---|---|---|---|
| 1 `read` | read | `00000` | — | yes |
| 2 `merge` | **refused** | `23514` | `gate_closed_when_issued` (a plain-column CHECK) | yes |
| 3 `projection_drift_attack` | **refused** | `P0001` | `mainline.fn_permit_merge_gate` (a PL/pgSQL trigger) | yes |
| 4 `admit` | admitted | `00000` | `merge_record.clearance_digest` computed server-side | yes |

Each beat carries its own `expected` block in the response, so `matched_expectation` is the
endpoint grading itself against a contract written before the run — all four `true` today. And
the run is non-destructive by construction: `transaction.disposition = "rolled_back"`, with a
`persistence_check` that reads row counts over every table the four beats can write, before the
transaction opened and after it was rolled back, and reports `identical: true`. A judge can run
it as many times as they like.

Beat 3 is the one to put in the film. Its label in the payload is *"THE ATTACK: force the
projected counter to zero out of band, then merge again."* The refusal message, verbatim from
the live response body:

> `MAINLINE: merge refused by mainline.fn_permit_merge_gate — re-derived open obligation count is 1 while the projected counter reads zero`

That is an agent corrupting the memory layer's own cached counter — exactly what a careless
`UPDATE` or a disarmed projector leaves behind — and the trigger **re-deriving the truth from
the base relations and refusing anyway**. The memory does not trust its own summary.

Beats 2 and 3 refusing through *different* mechanisms is by design, and the design is written
down before the demo: `packages/trappoint-conformance/REFUSAL_DEPTH.md` records that
`fn_permit_merge_gate` deliberately declines to decide when the projected counter agrees with
the re-derivation, so that the refusal on the ordinary path belongs to the named CHECK
constraint whose name is the exhibit. The live transcript shows precisely that split.

---

### R4 · `fn_refuse_mutation` — append-only welded to 17 tables

```
state:         LIVE
what it is:    One 4-line PL/pgSQL function that always raises, bound BEFORE UPDATE OR DELETE
               to 17 evidentiary tables. It names no column and reads no relation.
where:         verticals/mainline/db/migrations/0107_fn_refuse_mutation.sql (the function;
               mirrored at packages/trappoint-sql/refvertical/sql/0107_fn_refuse_mutation.sql) ·
               triggers at 0128, 0128a–0128j (11 tables) and 0145e, 0145f, 0149a, 0149b,
               0149y, 0149z (6 more)
verify in 60s: $CRDB "BEGIN; UPDATE mainline.permit_event SET actor_sub = actor_sub
                      WHERE seq >= 0; ROLLBACK;"
               → `ERROR: MAINLINE: this table is append-only; write a new row` / `SQLSTATE: P0001`
say this:      "Seventeen evidentiary tables refuse UPDATE and DELETE from every writer,
               including the cluster superuser. Measured: root cannot edit a permit event."
never say:     "Nothing can alter the record." A role holding DDL can drop the trigger. What
               that costs the attacker is row R4's last paragraph, and it is a different claim.
```

**Measured today, as `root`, the cluster superuser, inside an explicit transaction.** Pasted
unedited; the `BEGIN` line is included so it is visible that the refusal came from the statement
and not from a connection that never opened:

```
$ SELECT current_user, count(*) FROM mainline.permit_event;
  root | 8

$ BEGIN; UPDATE mainline.permit_event SET actor_sub = actor_sub WHERE seq >= 0; ROLLBACK;
BEGIN
ERROR: MAINLINE: this table is append-only; write a new row
SQLSTATE: P0001

$ BEGIN; DELETE FROM mainline.permit_event WHERE seq >= 0; ROLLBACK;
BEGIN
ERROR: MAINLINE: this table is append-only; write a new row
SQLSTATE: P0001

$ SELECT count(*) FROM mainline.permit_event;
  8
```

The count is 8 because that is what the local cluster happened to hold at the moment of the
probe; **the claim is not the number, it is that the number does not move.** Both attempts were
fenced in a transaction that was rolled back, and neither reached the rollback: the trigger
raised first, which is the point.

This is the claim that separates a trigger from a grant. Grants are cluster state and do not
survive a restore into a fresh cluster; an incident is exactly the moment somebody is granted
more than they should hold; and the owner role can always grant itself anything. The trigger
travels *with the schema*, survives a restore, and is independent of both the grant matrix and
the RLS policies. The rationale header of `0107_fn_refuse_mutation.sql` says so in the file.

**The honest boundary, stated because a judge will find it in one question.** The refusal is
`FOR EACH ROW`, so an `UPDATE` matching zero rows is a no-op that trivially changes nothing —
measured on the empty `refusal_ledger`, which returned `UPDATE 0` without firing. Nothing was
mutated, but the correct sentence is "no row can be altered", not "no statement is accepted".
And a principal holding DDL can `DROP TRIGGER`. The project measures that too rather than
asserting past it: `packages/trappoint-conformance/REFUSAL_DEPTH.md` records histories `CF-08`
and `CF-39` at **depth 1** — unweld the append-only trigger and the write succeeds. The
defence against the DDL-holder is not this trigger; it is the custody ledger, plus the fact
that no role in the lattice holds DDL (row R10).
`tests/integration/custody/nemesis/test_gate_attacks.py:99 ::test_a13_trigger_disable` runs that
attack — disable the gate, then merge a permit carrying an undischarged obligation — and makes
three separate assertions, of which only the first is the obvious one: that the merge was still
refused; that the refusal *named* `fn_permit_merge_gate`; and that the attack was **detected by
ledger check 11**, whose comment states the mechanism — *"The gate is self-attesting: its
`CREATE TRIGGER` text was sequenced into the ledger before anything it later refused, so an
exhibit can show the exact source of the mechanism — and its absence."* The claim against a
DDL-holder is attribution, not impossibility, and the test is written to assert exactly that and
no more.

**The provenance caveat that must travel with every `REFUSAL_DEPTH.md` citation on this page.**
That file is generated against the **reference** vertical (`trappoint-ref`, schema
`trappoint_ref`), and its own header records that six relations the reference tree names but does
not create were supplied as minimal stand-ins so the tree would apply at all — *"a matrix
measured on a patched schema is not a matrix measured on the shipped one."* So the depth numbers
are a measurement of the reference binding, not of `mainline_demo`. Cite them for the *shape* of
the finding (one named mechanism per path, and the project publishing that) and never as a
measurement of the deployed schema.

Shipping a generated file that contradicts our own architecture document's "depth three"
sentence is a credibility asset, and the close block should say so rather than route around it.

---

### R5 · Hash-chain enforcement triggers

```
state:         LIVE
what it is:    fn_permit_event_chain / fn_cr_event_chain refuse an appended event whose
               prev_digest does not equal the predecessor's stored chain_digest.
where:         packages/trappoint-sql/refvertical/sql/0105_fn_permit_event_chain.sql ·
               0106_fn_cr_event_chain.sql · triggers 0125, 0126
verify in 60s: $CRDB "SELECT tgname FROM pg_trigger WHERE tgname IN
               ('permit_event_chain','cr_event_chain');"  → both names returned
say this:      "The event chain is verified by the database on every append. A forged link is
               refused by the relation, not by a background auditor."
never say:     "The database computes the chain." The digest is a generated STORED column —
               W5 owns that row; this row is the trigger that refuses a bad LINK.
```

Two details worth the close block's attention. The predecessor comparison is written
`IS DISTINCT FROM`, not `<>`, because a NULL on either side makes `<>` evaluate to NULL, an
`IF` on NULL does not execute, and the guard would pass silently **on exactly the row it exists
to catch**. And the genesis exemption is taken by counting existing rows for the subject rather
than by trusting a sequence number, so both spellings of "first row" are covered and a later
row claiming genesis falls through to the predecessor lookup and is refused there, with
`UNIQUE (permit_id, prev_seq)` as the structural backstop.
`packages/trappoint-conformance/REFUSAL_DEPTH.md` records `CF-16` and `CF-17` refusing with
exhibit `mainline.fn_permit_event_chain`, and
`tests/integration/custody/nemesis/test_gate_attacks.py::test_a11_prev_digest_forgery` is the
adversarial case.

---

### R6 · `trappoint.explain_refusal` — the refusal explains itself, from the same engine

```
state:         LIVE
what it is:    A PL/pgSQL function returning JSONB: the minimal unsatisfiable subset and the
               nearest admissible alternative, computed by the engine that produced the refusal.
where:         packages/trappoint-sql/refvertical/sql/0119a_fn_explain_refusal.sql
               called at verticals/mainline/apps/demo-api/src/mainline_demo_api/refusal.py:141
               `_EXPLAIN_SQL: Final = "SELECT trappoint.explain_refusal(%s, %s, %s, %s)"`
verify in 60s: $CRDB "SELECT proname FROM pg_proc WHERE proname='explain_refusal';"
               → `explain_refusal`
say this:      "The database does not just refuse; it returns a structured reason set computed
               by the same engine that refused — and where it has no decomposition, it says so
               rather than inventing one."
never say:     "The API explains the refusal." It explicitly refuses to — see below.
never say:     "Every refusal comes back with a nearest admissible alternative." On the live
               demo's headline refusal it does not. Measured, and it is the next paragraph.
```

This is the row that most directly serves *agentic* memory: the refusal is machine-actionable.
`refusal.py`'s module docstring states the discipline in the negative, and it is worth quoting
because it is the opposite of what most systems do:

> "The API does not decompose refusals. If it did, the explanation could disagree with the
> refusal, and an explanation that can disagree with its refusal is worse than no explanation."

Two further properties, both checkable. The function **refuses to explain a refusal that has no
exhibit** — `p_constraint` empty raises `P0001` with *"a refusal with no exhibit is not
evidence"*, and a subject that does not exist raises rather than guessing. And because a
PL/pgSQL function that can itself `RAISE` would abort the caller's transaction, `refusal.py`
wraps the call in its own `SAVEPOINT` — which is what lets the demo hold **one** transaction
open across all four beats of the live gate run.

**The measured limit, which must travel with this row wherever it goes.** On the live demo's
*strongest* refusal — beat 3, the projection-drift attack — `explain_refusal` returns
`diagnosis: "none"`, `naa: null`, `naa_reason: "not_computable"`, and a single reason-set atom
of kind `capability_gap` naming `mainline.fn_permit_merge_gate`
(`evidence/demo/live-beats.json` → `gate_run.beat_three_diagnosis`). It has no declarative
decomposition for that trigger and **says so, instead of shipping a plausible superset labelled
declarative**. The evidence file annotates this itself:

> "That is a Product-Readiness point, not an embarrassment."

Agreed, and the close block should use it that way. A refusal-explainer that returns
`not_computable` on the one case it cannot decompose is more trustworthy than one that always
has an answer — and it is exactly the distinction row R7's closed vocabulary exists to keep
enforceable.

---

### R7 · The refusal ledger's append-only guard

```
state:         REPO
what it is:    fn_refusal_ledger_guard refuses UPDATE/DELETE outright and additionally
               validates every INSERT's reason set against a closed vocabulary.
where:         packages/trappoint-sql/refvertical/sql/0119b_fn_refusal_ledger_guard.sql ·
               trigger 0133_trg_refusal_ledger_append_only.sql
               (BEFORE INSERT OR UPDATE OR DELETE ... FOR EACH ROW)
verify in 60s: $CRDB "SELECT tgname FROM pg_trigger WHERE tgname='trg_refusal_ledger_append_only';"
               → `trg_refusal_ledger_append_only`
say this:      "The ledger of refusals is itself append-only, and it rejects a refusal whose
               reason set is empty or names a fact family the schema cannot represent."
never say:     "It has been exercised in the demo." mainline.refusal_ledger holds 0 rows on the
               measured cluster; the guard is installed and its INSERT arm is untested there.
```

Marked **REPO** rather than LIVE, honestly: the table is empty on the measured cluster
(`SELECT count(*) FROM mainline.refusal_ledger` → `0`), so the row-level guard has not fired
there. What makes it worth a row anyway is its shape. It is the only append-only guard in the
schema that also polices `INSERT`, and it enforces three separate things a lesser guard would
not: the reason set must be a JSON *array*; it must be non-empty (*"a refusal with no reason
set is not evidence"*); every atom must name one of five modelled fact families
(`obligation`, `clause`, `event`, `authority_gap`, `capability_gap`); and every key must come
from a closed vocabulary. A refusal record that cannot be decomposed is refused at write time.

---

### R8 · Row-level security, and `FORCE` — the table refuses its own owner

```
state:         LIVE
what it is:    4 tables with RLS enabled, all 4 also FORCE, carrying 25 policies (20 permissive,
               5 restrictive).
where:         verticals/mainline/db/migrations/0181, 0181a, 0181b–0181h (permit) ·
               0183, 0183a, 0183b–0183h (change_request) · 0185, 0185a, 0185b–0185h
               (disposition) · 0187_standing_rls_enable, 0187a_standing_rls_force,
               0187b–0187e (standing) · declared once in verticals/mainline/db/RLS-MATRIX.yaml
verify in 60s: $CRDB "SELECT count(*) FROM pg_class WHERE relrowsecurity;" → `4`
               $CRDB "SELECT count(*) FROM pg_class WHERE relforcerowsecurity;" → `4`
               $CRDB "SELECT count(*) FROM pg_policies;" → `25`
say this:      "Four tables carry row-level security and all four FORCE it, so the policy binds
               the table's own owner. Twenty-five policies, declared in one matrix file the
               test suite asserts the cluster against."
never say:     "RLS defends against a rogue administrator." Banned by name — see below.
```

The four tables and their policy counts, and the reason each one earns RLS at all — RLS is on a
table only where two principals who **both hold the privilege** must see different rows:

| table | policies | why |
|---|---|---|
| `mainline.permit` | 7 | site scoping across a fleet, plus the gate's write set |
| `mainline.change_request` | 7 | the same idiom, applied to the second gated subject |
| `mainline.disposition` | 7 | `peer_blind` — a signer may not read what another signer decided *before* signing themselves |
| `mainline_meas.standing` | 4 | `standing_blind` — a person-measure a signer may not read laterally |

`peer_blind` is the case that shows what RLS is actually *for* here. A signer holds `SELECT` on
`disposition` and always will; what they must not hold is the ability to read Dave's signature
before producing their own. **That is access control doing epistemics, not access control
protecting data** — and it is a genuinely unusual use of the feature.

**FORCE is the detail that matters, and it is demonstrable in under a minute.** Measured today
in an isolated scratch database (`w_w6`), created for this purpose and touching nothing in
`mainline_demo`:

```sql
CREATE TABLE w6_force_demo (id INT PRIMARY KEY, v STRING);
INSERT INTO w6_force_demo VALUES (1,'a'),(2,'b');
ALTER TABLE w6_force_demo OWNER TO w6_owner;
ALTER TABLE w6_force_demo ENABLE ROW LEVEL SECURITY;
SET ROLE w6_owner; SELECT current_user, count(*) FROM w6_force_demo;
ALTER TABLE w6_force_demo FORCE ROW LEVEL SECURITY;
SET ROLE w6_owner; SELECT current_user, count(*) FROM w6_force_demo;
RESET ROLE;        SELECT current_user, count(*) FROM w6_force_demo;
```

Output, pasted unedited:

```
    who    | owner_sees
-----------+-------------
  w6_owner |          2          <- ENABLE only: the owner is exempt

    who    | owner_sees_under_force
-----------+-------------------------
  w6_owner |                      0          <- after FORCE: the owner is inside the policy set

  who  | admin_sees_under_force
-------+-------------------------
  root |                      2          <- the cluster admin still reads everything
```

Two to zero. Without `FORCE` the owner is exempt and RLS is decoration on any table whose owner
is reachable; with `FORCE` the owner is inside the policy set like everybody else. That is why
all four tables carry it and why the matrix file prefers a *named* `view_owner_read` policy over
dropping `FORCE` to achieve the same reads: `FORCE` plus a named policy leaves one diffable,
revocable object a reviewer can see and a test can assert, where no `FORCE` leaves a silent,
unnameable exemption.

**The honesty counterpoint, measured in the same scratch database, and it is mandatory.**
`root` — a cluster admin — reads all 2 rows under `FORCE` with no policy. RLS is evaluated by
the same server the administrator owns. `docs/submission/MUST-NOT-CLAIM.md` names
"row-level security against a rogue admin" as a banned sentence, `scripts/demo/claim_hygiene.py`
rule `MNC-01` fails the build on it, and the sanctioned replacement is: *"RLS is tenancy and
least privilege — it stops a confused query, not the administrator. Against the administrator
the claim is tamper-evidence."*

**And the second half of the same honesty, because a judge running one query will find it.**
On the local cluster the four RLS tables report `relowner = root`:

```sql
SELECT n.nspname||'.'||c.relname AS rel, pg_get_userbyid(c.relowner) AS owner,
       c.relrowsecurity AS rls, c.relforcerowsecurity AS forced
  FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
 WHERE c.relrowsecurity ORDER BY 1;

           rel            | owner | rls | forced
--------------------------+-------+-----+---------
  mainline.change_request  | root  |  t  |   t
  mainline.disposition     | root  |  t  |   t
  mainline.permit          | root  |  t  |   t
  mainline_meas.standing   | root  |  t  |   t
```

The *schemas* are owned by `mainline_owner` (`0008a_owner_business.sql`, verified:
`SELECT nspname, pg_get_userbyid(nspowner) FROM pg_namespace WHERE nspname LIKE 'mainline%'`
returns `mainline_owner` for all five). The tables are owned by whoever applied the chain, and
the chain is applied as `root`. So on **this** cluster `FORCE` is not observable against the
table owner, because that owner is a superuser and superusers bypass RLS regardless. The
correct claim is therefore the one the scratch-database demonstration above proves and this
paragraph does not weaken: **`FORCE` is set on all four tables, which is what removes the
owner's exemption for any non-superuser owner.** Saying it that way costs nothing and survives
the query. Saying "the table refuses `root`" would not.

**Paired conformance case.** `packages/trappoint-conformance/cases/cf22_gate_under_force_rls.py`
runs the entire gate transaction with `FORCE` active, and is written so it **cannot pass by
absence**: if the operator declared the `policy:mainline.permit` capability and `pg_policies`
holds nothing, the case *fails* naming the missing policy rather than skipping green. Three
integration tests carry the CF-22 name and all three passed in today's run
(`test_cf22_the_gate_transaction_survives_forced_rls`,
`test_cf22_dropping_the_insert_policy_refuses_with_42501`,
`test_cf22_dropping_the_update_policy_is_silent_not_refused`).

That third test is the most valuable thing in the RLS band and it should survive into the close
block if there is room. The project **measured that the documented symptom is wrong**: dropping
an INSERT policy raises `42501`, but dropping an UPDATE policy **raises nothing at all** — a
`USING` clause filters, and only a `WITH CHECK` violation on a new row raises, so with no
visible row there is nothing to refuse. The test asserts `rowcount == 0 with no exception`
rather than the `42501` the architecture predicted, precisely so that the finding cannot be
"repaired" later by relaxing it. A silent zero-row UPDATE is strictly worse than a refusal,
because it would let a counter stay zero and a permit merge carrying an open obligation.

**One stale pointer found while auditing this row, reported and not repeated.**
`cf22_gate_under_force_rls.py:22-24` says the policy-drop half *"belongs to the unwelding suite …
registered there as the `force-rls-without-write-policy` mutation, and `REFUSAL_DEPTH.md` carries
the result."* Measured: it is not there.

```bash
grep -c force-rls-without-write-policy packages/trappoint-conformance/unweld/mutations.py  # 0
grep -ci rls packages/trappoint-conformance/REFUSAL_DEPTH.md                               # 0
grep -c "Mutation(" packages/trappoint-conformance/unweld/mutations.py                     # 21
```

The 21 registered mutations are constraints and triggers only, and `mutations.py:22` says why
that is deliberate: *"Grants and RLS are absent from this matrix, deliberately … Dropping a
`REVOKE` while connected as `root` would measure nothing at all, because `root` was never subject
to it."* The policy-drop half **does exist** — it is
`tests/integration/schema/test_mi_rls.py::test_cf22_dropping_the_insert_policy_refuses_with_42501`,
which passed today. So the capability is real and the docstring points at the wrong file. **The
close block must cite the test path, never the unwelding matrix, for this claim.** This is a
one-line source-comment fix and it is not this worker's file to edit; it is logged here for the
orchestrator.

---

### R9 · The deliberate RLS exclusion — two CDC sources, with the absence recorded in the database

```
state:         LIVE
what it is:    mainline_ops.outbox and mainline_ops.site_register_signal deliberately carry NO
               row-level security, and a COMMENT ON TABLE says so where a reader looks for a
               policy and does not find one.
where:         verticals/mainline/db/migrations/0198x_no_rls_on_cdc_sources.sql ·
               declared under `rls_forbidden` in verticals/mainline/db/RLS-MATRIX.yaml
verify in 60s: $CRDB "SELECT obj_description('mainline_ops.outbox'::regclass);"
               → begins `NO ROW LEVEL SECURITY, BY DESIGN AND BY PLATFORM LAW.`
say this:      "Two tables are deliberately excluded from row-level security, and the reason is
               a comment stored in the database next to the table it governs."
never say:     "RLS is applied everywhere." It is applied on four tables, refused on two, and
               absent from the rest for a stated reason.
```

A blanket control is less credible than a scoped one, and this is the row that proves the scope
was chosen rather than defaulted. CockroachDB v26.2's own documentation states that CDC queries
are **not supported** on tables using RLS and **will fail**, and that CDC messages are not
filtered by RLS in any case. So enabling RLS on the one changefeed-query source would buy no
confidentiality and would stop the event spine — and it would stop it at the next changefeed
*restart*, not at the `ALTER`, separating the change from the outage by however long the
current feed happens to survive.

Three things make this a strong row rather than an excuse. The absence is **defensible as well
as necessary**: the outbox payload carries pointers and digests only, never clause or narrative
text, and the table carries a 30-day row-level TTL bounding even that exposure. The claim is
**retrievable from the database**, not just from a design document — the same move
`0009x_covenant_comment.sql` makes for the separation covenant. And the absence is **asserted
by tests in the negative direction**:
`test_mi_rls.py::test_the_cdc_sources_have_no_row_level_security` and
`::test_the_forbidden_tables_are_never_rls_enabled_anywhere_in_the_tree`. Some of this system's
guarantees are about what is *not* there, and those decay silently unless something checks.

---

### R10 · The nine-role lattice, the public revokes, the privileges floor, the covenant

```
state:         LIVE (roles, revokes, floor, covenant — all in the 271-file chain)
               REPO (the full GRANTS.yaml table-privilege matrix — see the boundary below)
what it is:    Nine NOLOGIN roles as a separation-of-duties lattice, a five-schema revoke of
               PUBLIC, a default-privileges floor, and a machine-readable covenant COMMENT.
where:         packages/trappoint-sql/refvertical/sql/0006a–0006i (reference names) ·
               verticals/mainline/db/migrations/0006a–0006i (deployed names) ·
               0007a–0007e (public revokes) · 0008a–0008e (owners) · 0009a–0009d (usage) ·
               0009e_default_privileges_floor.sql · 0009f · 0009x_covenant_comment.sql ·
               declared in verticals/mainline/db/GRANTS.yaml
verify in 60s: $CRDB "SELECT rolname, rolcanlogin FROM pg_roles WHERE rolname IN
               ('mainline_migrator','mainline_owner','agent_gate','agent_projector',
                'agent_recaller','svc_disposition','mainline_auditor','auditor_ro',
                'quality_assurance') ORDER BY 1;"
               → 9 rows, `rolcanlogin` = `f` on every one
say this:      "Nine roles, none of which can log in, split the duties: the role that detects an
               obligation cannot create one, the role that creates one cannot dispose of it, and
               the role that certifies the books has no write path to them."
never say:     "The grant matrix is applied on the deployed cluster." It is not — the roles and
               the revokes are, the §4 table-privilege rows are not. See the boundary below.
```

The reference vertical's nine role slots and the names the deployed mainline binding renders
them to — the lattice is a *template parameter*, which is why the same separation survives a
rebinding:

| slot (`0006x`) | reference name | deployed name |
|---|---|---|
| migrator | `tref_migrator` | `mainline_migrator` |
| owner | `tref_owner` | `mainline_owner` |
| gate | `tref_gate` | `agent_gate` |
| projector | `tref_projector` | `agent_projector` |
| recaller | `agent_recaller` | `agent_recaller` |
| disposer | `tref_disposer` | `svc_disposition` |
| auditor | `trappoint_ref_auditor` | `mainline_auditor` |
| reader | `tref_reader` | `auditor_ro` |
| qa | `quality_assurance` | `quality_assurance` |

**All nine measured present, all nine `NOLOGIN`.** They are privilege containers reached by
membership, not accounts — so there is no credential whose theft yields the role.

Three measured floor properties, each one query:

```
public holds table privileges in the 5 app schemas ......... 0
any role holds DELETE on mainline / mainline_meas .......... 0
SECURITY DEFINER routines ................................. 0
```

*No role holds `DELETE` on anything* is the first of the three layers append-only rests on;
`fn_refuse_mutation` (R4) is the second, and it is deliberately independent of the first so
that a restore into a fresh cluster — which does not carry grants — still refuses.

The **covenant comment** (`0009x`) is the piece worth showing a judge, because it makes the
separation-of-duties promise queryable out of the database rather than readable out of a design
doc:

> "1. The role that detects a precursor may never write one … 2. The role that materialises an
> obligation may never dispose of it … 3. The role that certifies the books has no write path to
> them … Enforced by grants, by trigger, and by RLS, in that order."

**The boundary, stated plainly, and every clause of it quoted rather than paraphrased.**
`verticals/mainline/db/GRANTS.yaml:237` records that the table-privilege matrix is not applied to
the deployed cluster by the deploy path:

> "deploy.sh runs cloud_chain.py then seed_demo.py and invokes cloud_roles.py out of band, and
> `grants apply` is not pointed at the demo cluster at all."

and, separately measured and recorded in the same file at line 287:

> "MEASURED on a freshly migrated database: `information_schema.table_privileges` for
> `agent_gate`, `svc_disposition` and `auditor_ro` returns NO ROWS. These three carry POLICY
> SCOPE and no table privilege."

So the roles, the `PUBLIC` revokes, the default-privileges floor and the covenant comment are
migrations and are therefore **LIVE**; the §4 table-privilege matrix is **REPO**.

The same file also records, unprompted, that the demo login `mainline_api` is made a member of
three of the lattice roles for RLS scope. Measured today on the local cluster:

```sql
SELECT r.rolname AS member, g.rolname AS member_of
  FROM pg_auth_members m JOIN pg_roles r ON r.oid=m.member JOIN pg_roles g ON g.oid=m.roleid
 WHERE r.rolname = 'mainline_api' ORDER BY 2;

    member    |   member_of
--------------+------------------
  mainline_api | agent_gate
  mainline_api | auditor_ro
  mainline_api | svc_disposition
```

**For the demo credential the separation of duties therefore does not hold** — one login unions
three principals. `GRANTS.yaml` says so itself and gives the reason, which is a real one:
*"RLS SCOPE, NOT PRIVILEGE … Those three roles are the principals the demo impersonates, one per
beat."* Under `FORCE`, a policy written `TO agent_gate` matches only members of `agent_gate`, and
the file records what the alternative cost: *"A bare `GRANT SELECT ON mainline.permit` therefore
buys ZERO ROWS, SILENTLY — which is the worst failure an audit surface can have, because it is
indistinguishable from a clean site."* **The close block must not claim separation of duties for
the demo login.** It may claim the lattice enforces it, and that the demo deliberately collapses
it into one identity with the collapse recorded in the file that defines the lattice.

---

### R11 · Recursive CTEs

```
state:         REPO
what it is:    Four executable WITH RECURSIVE statements walking two different DAGs — the
               event/blame DAG and the clause commit DAG — each explicitly depth-bounded.
where:         verticals/mainline/db/queries/closure_write.sql:152 ·
               verticals/mainline/packages/mainline-domain/src/mainline_domain/registry/sql.py:57 ·
               .../mainline_domain/diachronic/origin.py:133 ·
               verticals/mainline/packages/mainline-recall-agent/src/mainline_recall_agent/run/channels.py:149
verify in 60s: grep -rn "^WITH RECURSIVE" verticals/mainline/db/queries verticals/mainline/packages \
                 --include=*.sql --include=*.py
               → exactly 4 lines, the four sites above. (The anchor matters: an unanchored
                 grep returns 9, because five further matches are prose in comments and
                 docstrings describing these same four statements.)
say this:      "The blame closure is computed by a recursive CTE that feeds its own INSERT —
               one statement walks the ancestry DAG and writes the summary."
never say:     "0034_event_edge.sql contains a recursive CTE." Its CTE is inside a comment. §1.3.
```

| site | walks | shape |
|---|---|---|
| `closure_write.sql:152` | the event DAG upward from a clause version's active blame edges | `WITH RECURSIVE … INSERT INTO … SELECT`, `UNION`, `depth < 64` |
| `registry/sql.py:57` (`ANCESTRY_SQL`) | `mainline.commit_edge`, every reachable commit | `UNION`, no bound — the relation is finite and acyclic by construction |
| `diachronic/origin.py:133` (`FIRST_PARENT_ANCESTRY_SQL`) | the first-parent chain from one commit | `UNION ALL`, `parent_ord = 0`, parameterised `depth_bound` |
| `run/channels.py:149` | the recall scope hierarchy upward | scope walk with depth |

`closure_write.sql` is the one to name. A **recursive CTE feeding a top-level `INSERT`** is not
a routine construct, and the file records that it was *executed as written* against
CockroachDB CCL v26.2.5 on 2026-08-10 by
`tests/integration/schema/test_mi_blame.py::test_the_writer_projects_a_real_blame_dag` over a
three-generation event DAG, producing the correct closure. The measured plan is committed at
`verticals/mainline/db/queries/EXPLAIN-ASSERTIONS.md`, and the file carries a stated fallback
if a later CockroachDB version refuses the combination — one extra round trip, same
derivations. Two design details are worth a sentence each: `UNION` rather than `UNION ALL`
collapses diamond ancestry so a self-edge terminates instead of looping, and CockroachDB has no
`CYCLE` clause, which is why every walk here carries an explicit depth bound rather than
relying on one.

**Executed today, so the row is a measurement and not a reading.** `ANCESTRY_SQL`'s shape, run
against `mainline_demo` with a literal seed in place of the bound parameter:

```sql
WITH RECURSIVE reachable(commit_id) AS (
    SELECT (SELECT commit_id FROM mainline.commit_obj ORDER BY 1 DESC LIMIT 1)
  UNION
    SELECT e.parent_id FROM mainline.commit_edge e JOIN reachable r ON e.child_id = r.commit_id)
SELECT count(*) AS reachable_commits FROM reachable;

  reachable_commits
---------------------
                  1
```

The recursion executes; `1` is a fact about how many commits the demo seed holds, not about the
query. One platform detail found while writing that probe and worth a line, because it is the
kind of thing a judge who tries it will hit: **CockroachDB rejects `LIMIT` inside a recursive
CTE's base term** (`42601`), which is why the seed above is a scalar subquery. That is also why
`origin.py` passes its bound as a parameter rather than shaping the base case.

---

### R12 · Guarded `RETURNING` — a compare-and-swap, and a defect that must not come back

```
state:         LIVE
what it is:    An UPDATE ... RETURNING used as a compare-and-swap on the permit head sequence,
               plus a documented guard keeping a *future* RETURNING from reintroducing a
               measured row-factory defect.
where:         verticals/mainline/db/migrations/0117_proc_merge_permit.sql:190 and
               0118_proc_merge_change_request.sql:190 — `RETURNING head_seq INTO v_new_head`
               inside the PL/pgSQL procedure (the CAS the live demo runs)
               verticals/mainline/apps/demo-api/src/mainline_demo_api/transitions.py:838
               `"UPDATE mainline.permit SET state = %s, head_seq = %s "
                "WHERE permit_id = %s AND head_seq = %s RETURNING head_seq"`
               guard documented at .../refusal.py:70
verify in 60s: grep -rn "RETURNING" verticals/mainline/apps/demo-api/src
               → transitions.py:838 (the statement) and refusal.py:70 (the guard)
say this:      "The merge is a compare-and-swap: the UPDATE names the head sequence it expects
               and RETURNING proves it landed. On CockroachDB that is not a style choice —
               GET DIAGNOSTICS ROW_COUNT is unimplemented, so RETURNING ... INTO is how a
               PL/pgSQL procedure detects a zero-row UPDATE at all."
never say:     "RETURNING is used throughout." There is exactly one in the live request path.
```

Three distinct things share this row and the distinctions are the point.

**The platform reason, measured today in a throwaway database rather than asserted.**
`0117_proc_merge_permit.sql` says in its own comment that `RETURNING … INTO` is used "because
`GET DIAGNOSTICS … ROW_COUNT` is unimplemented on this platform". Verified:

```sql
CREATE PROCEDURE p() LANGUAGE plpgsql AS $$ DECLARE n INT;
BEGIN UPDATE t SET v=1 WHERE id=1; GET DIAGNOSTICS n = ROW_COUNT; END $$;

ERROR: unimplemented: PL/pgSQL GET DIAGNOSTICS statement is not yet supported
SQLSTATE: 0A000
HINT: See: https://go.crdb.dev/issue-v/117410/v26.2
```

and the substitute works, in the same database, as a real compare-and-swap:

```sql
CREATE PROCEDURE cas(a_id INT, a_expect INT) LANGUAGE plpgsql AS $$ DECLARE n INT;
BEGIN
  UPDATE t SET v = a_expect + 1 WHERE id = a_id AND v = a_expect RETURNING v INTO n;
  IF n IS NULL THEN RAISE EXCEPTION USING ERRCODE='P0001', MESSAGE='CAS failed: the head moved';
  END IF;
END $$;

CALL cas(1, 0);   -- CALL      (v: 0 -> 1)
CALL cas(1, 0);   -- ERROR: CAS failed: the head moved   SQLSTATE: P0001
```

The scratch database was created for this probe and dropped immediately after; `mainline_demo`
was not touched. This is the strongest form the row can take: the comment in the migration is a
claim about the platform, and the claim is now a pasted transcript.

**The real use.** `transitions.py:838` issues the state move with the expected `head_seq` in its
`WHERE` clause and `RETURNING head_seq` as proof of effect. Because the preceding `INSERT` into
`permit_event` is itself the compare-and-swap — `CONSTRAINT linear UNIQUE (permit_id, prev_seq)`
means two writers that both read head *n* cannot both append after it, and the second gets
`23505` — a zero-row result here is *unreachable* inside one SERIALIZABLE transaction. So the
code raises a `RuntimeError` naming itself a defect rather than reporting a gate refusal. That
discipline — never let an impossible internal state masquerade as a product refusal — is what
keeps the refusal evidence trustworthy.

**The guard.** `refusal.py:70` is not a use of `RETURNING`; it is a note forbidding a careless
future one. The module's `SAVEPOINT` / `ROLLBACK TO` / `RELEASE` statements return no rows and
so cannot today misread a row shape — but they are routed through the same explicit
`tuple_row` helper anyway, because *"a later edit that adds a `RETURNING` clause to one of them
must not be able to reintroduce the defect quietly."* The defect was real and is recorded at
`evidence/deploy/rowfactory-defect.json`: production connections open with `dict_row`, the
explain call's single column is named `explain_refusal`, and a positional read of it raised
`KeyError: 0` on beats 2 and 3 of *every* gate run. The test that pins it is
`verticals/mainline/apps/demo-api/tests/test_refusal_row_factory.py` — note that `refusal.py`'s
docstring names it by the short form `tests/test_refusal_row_factory.py`, which is the path
relative to that app, not to the repository root; the repo-root path is the one above and is the
one a judge should be given. There is also a repo-wide scanner for the class of defect,
`scripts/qa/row_factory_ratchet.py`, whose header states the rule as *"not 'never inherit' but
'always declare'"* and publishes the count of undeclared statements as a number that may fall and
may not rise.

Marked LIVE for the statement; the guard is a repository property and should be described as
one.

---

## 3. THE OPEN FINDING — DOCUMENTED, UNTOUCHED, AND NOT MINE TO CLOSE

**The standing `materialise_checks` / `exposure_receipt` INSERT gap remains OPEN. No grant was
added, widened, or proposed by this worker.**

Measured today on `mainline_demo`:

```sql
SELECT grantee, table_schema||'.'||table_name AS obj,
       string_agg(privilege_type,',') AS privs
  FROM information_schema.table_privileges
 WHERE table_name IN ('exposure_receipt','exposure_line','blocking_check') AND grantee <> 'root'
 GROUP BY 1,2 ORDER BY 1,2;

    grantee    |            obj            |     privs
  -------------+---------------------------+----------------
    admin      | mainline.blocking_check   | ALL
    admin      | mainline.exposure_line    | ALL
    admin      | mainline.exposure_receipt | ALL
    mainline_api | mainline.blocking_check   | SELECT,UPDATE
    mainline_api | mainline.exposure_line    | SELECT
    mainline_api | mainline.exposure_receipt | SELECT
```

and the same answer from the function the driver would actually get its `42501` from — which is
the form to prefer, because it resolves inheritance rather than reading a matrix:

```sql
SELECT t AS relation,
       has_table_privilege('mainline_api', t, 'SELECT') AS sel,
       has_table_privilege('mainline_api', t, 'INSERT') AS ins,
       has_table_privilege('mainline_api', t, 'UPDATE') AS upd,
       has_table_privilege('mainline_api', t, 'DELETE') AS del
  FROM (VALUES ('mainline.blocking_check'),('mainline.exposure_receipt'),
               ('mainline.exposure_line'),('mainline.permit_event'),
               ('mainline.disposition')) AS v(t);

         relation          | sel | ins | upd | del
---------------------------+-----+-----+-----+------
  mainline.blocking_check  |  t  |  f  |  t  |  f
  mainline.exposure_receipt|  t  |  f  |  f  |  f
  mainline.exposure_line   |  t  |  f  |  f  |  f
  mainline.permit_event    |  t  |  t  |  f  |  f
  mainline.disposition     |  t  |  t  |  f  |  f
```

The gap is three cells wide and it is exactly the three the finding names: **no `INSERT` on
`blocking_check`, `exposure_receipt` or `exposure_line`.** The two the demo's headline beat
actually needs — `permit_event` and `disposition` — are granted, which is why beat 4 admits.

`transitions.py:925` issues `INSERT INTO mainline.exposure_receipt` and `transitions.py:1003`
issues `INSERT INTO mainline.exposure_line`; the login holds `SELECT` on both and nothing more.
`has_table_privilege` resolves role membership, so the `f` above is the answer *after*
inheritance through `agent_gate`, `auditor_ro` and `svc_disposition` — **neither the direct route
nor the inherited route supplies the INSERT here**. `GRANTS.yaml` carries the finding inline as a
`census_note` on both rows (lines 646 and 649) and states the reasoning at length:

> "That is R4b of the lead plan, OPEN: either the path is unreachable from the deployed surface
> or it is a 42501 waiting for the first judge who drives it. NO GRANT IS ADDED HERE until W1's
> census or W4's probe establishes which — an unreachable code path and a missing privilege look
> identical from a test's side and are different findings."

**One stale detail in that note, reported because this census's own rule is to report them.**
The `census_note` cites `transitions.py:891` and `:969`; the statements are today at `:925` and
`:1003`. The note is right about the statements and stale about the offsets. The offsets above
were measured today with `grep -n "INSERT INTO mainline.exposure_receipt" …`. **No edit was made
to `GRANTS.yaml`.**

The reason it stays open is a decision, not an oversight, and the submission should say so:
widening the write surface of an endpoint served by a Lambda Function URL with
`authorization_type = NONE` is the founder's call and he has not made it. Lead plan R7 places it
out of scope by construction.

---

## 4. WHAT THIS CENSUS REFUSES TO CLAIM

Collected so the close block can copy the negative statements as readily as the positive ones.
Every line here was checked against `docs/submission/MUST-NOT-CLAIM.md` and
`scripts/demo/claim_hygiene.py`.

| tempting | why it is false | say instead |
|---|---|---|
| "59 triggers" | 39 objects, 59 (trigger, event) pairs | "39 row-level triggers, 59 trigger-event pairs" |
| "ten tables refuse mutation" | measured 17 | "seventeen evidentiary tables" |
| "RLS defends against a rogue admin" | banned, `MNC-01`; admin reads through `FORCE` — measured | "RLS is tenancy and least privilege; against the administrator the claim is tamper-evidence" |
| "nothing can alter the record" | a DDL holder can drop the trigger; `REFUSAL_DEPTH.md` measures depth 1 for `CF-08`/`CF-39` | "no *row* can be altered by any writer, and an attempt to remove the mechanism is itself attributed" |
| "the write fails twice over" | the architecture's depth-3 sentence; the project's own unwelding harness measured depth 1 on 9 of 9 gated merge-gate histories | "one named mechanism refuses on the ordinary path and a different one on the drift path — and we publish the matrix that says so" |
| "the grant matrix is applied in production" | `GRANTS.yaml:237` — "`grants apply` is not pointed at the demo cluster at all" | "roles, revokes and the privileges floor are live; the table-privilege matrix is declared and applied locally" |
| "the table refuses `root`" (of RLS) | the four RLS tables' `relowner` is `root` on the measured cluster, and superusers bypass RLS regardless of `FORCE` | "`FORCE` is set on all four, which removes the owner's exemption for any non-superuser owner — demonstrated 2 rows → 0 in a scratch database" |
| "the RLS policy-drop case is in the unwelding matrix" | it is not; `cf22`'s docstring points at the wrong file — measured, 0 hits in `mutations.py` and `REFUSAL_DEPTH.md` | cite `test_mi_rls.py::test_cf22_dropping_the_insert_policy_refuses_with_42501`, which passed today |
| "`GET DIAGNOSTICS ROW_COUNT` tells the procedure how many rows moved" | unimplemented on v26.2.5 — `0A000`, issue 117410, measured | "`RETURNING … INTO` is the compare-and-swap detector, because the platform has no `ROW_COUNT`" |
| "separation of duties holds for the demo" | `mainline_api` is a member of both `agent_gate` and `svc_disposition` | "the lattice enforces separation; the single demo login deliberately unions three principals, and `GRANTS.yaml` records it" |
| "`0034_event_edge.sql` uses a recursive CTE" | comment-only | name `closure_write.sql:152` |
| "the API explains the refusal" | it explicitly refuses to | "the database returns the reason set, computed by the engine that refused" |
| "every refusal returns a nearest admissible alternative" | the live demo's headline refusal returns `naa: null`, `naa_reason: not_computable` | "it returns the reason set, and where it has no decomposition it reports `not_computable` rather than inventing one" |
| "RLS is applied everywhere" | 4 tables on, 2 deliberately forbidden | "four tables, and two excluded on the record" |

---

## 5. DETECTORS, FOR R6 RE-DERIVABILITY

Lead plan R6 requires every new row to be re-derivable by
`scripts/submission/capture_tool_evidence.py` rather than hand-maintained. Proposed row keys and
their exact detectors, for a follow-up worker to add. **No generator file was modified by this
worker, and no ratchet was touched.**

| proposed key | verdict | detector |
|---|---|---|
| `crdb_plpgsql_functions` | EXERCISED | SQL: `pg_proc ⋈ pg_language WHERE lanname='plpgsql' AND prokind='f'` → expect ≥ 26 |
| `crdb_plpgsql_procedures` | EXERCISED | same with `prokind='p'` → expect ≥ 2 |
| `crdb_triggers` | EXERCISED | SQL: `count(*) FROM pg_trigger WHERE NOT tgisinternal` → 39; and `information_schema.triggers` → 59. Record **both**. |
| `crdb_row_level_security` | EXERCISED | SQL: `count(*) FROM pg_class WHERE relrowsecurity` and `… relforcerowsecurity` → 4 / 4 |
| `crdb_rls_force` | EXERCISED | assert `relforcerowsecurity` count equals `relrowsecurity` count |
| `crdb_rls_policies` | EXERCISED | SQL: `count(*) FROM pg_policies` → 25, and `WHERE permissive='restrictive'` → 5 |
| `crdb_rls_deliberate_exclusion` | EXERCISED | SQL: `obj_description('mainline_ops.outbox'::regclass) LIKE 'NO ROW LEVEL SECURITY%'` |
| `crdb_role_lattice` | EXERCISED | SQL: the nine `rolname` values, assert `rolcanlogin = false` on all nine |
| `crdb_privilege_floor` | EXERCISED | SQL: public table-privileges in the 5 app schemas = 0; `DELETE` grants in `mainline`/`mainline_meas` = 0 |
| `crdb_no_security_definer` | EXERCISED | SQL: `count(*) FROM pg_proc WHERE prosecdef AND lanname='plpgsql'` → 0 |
| `crdb_recursive_cte` | EXERCISED | grep `^WITH RECURSIVE` (anchored, to exclude the 5 prose mentions) over `verticals/mainline/db/queries` and `verticals/mainline/packages` → 4 sites |
| `crdb_returning_cas` | EXERCISED | grep `RETURNING` over `verticals/mainline/apps/demo-api/src` → `transitions.py:838`; and `RETURNING .* INTO` over `db/migrations/0117`, `0118` → 2 sites |
| `crdb_rendered_object_per_file` | EXERCISED | filesystem, no cluster: `ls db/migrations \| grep -c _fn_` = 26, `_proc_` = 2, `_trg_` = 39, `_policy_` = 25 — each must equal its catalog count |
| `crdb_live_procedure_call` | EXERCISED | HTTP, no credential: `POST /v1/demo/gate-run` → `statement_refs[]` contains `{"kind":"procedure","object":"mainline.merge_permit"}` and `…"trappoint.explain_refusal"`, `data.verdict == "PROVEN"` |

---

## 6. THE THREE SENTENCES THIS DOMAIN CONTRIBUTES TO THE CLOSE BLOCK

Ordered by lead plan R5 — the store/retrieve/act loop first, breadth never. Each is
sub-minute-checkable by the row above it.

1. **"The database refuses the merge."** Twenty-six PL/pgSQL functions and two procedures,
   welded by thirty-nine row-level triggers, put the gate inside the relation. On the live
   origin, `POST /v1/demo/gate-run` beat 3 forces the projected obligation counter to zero out
   of band and re-attempts the merge; `mainline.fn_permit_merge_gate` re-derives the count from
   the base relations and refuses with `P0001`. *The memory layer does not trust its own
   summary.* — R3, `evidence/demo/live-beats.json`, verdict `PROVEN`, re-run 2026-08-16.

2. **"And it refuses the cluster superuser."** Seventeen evidentiary tables carry an append-only
   trigger that raises unconditionally; `root` cannot `UPDATE` or `DELETE` a permit event —
   measured today, both verbs, `P0001`, row count unmoved. Four tables carry row-level security
   and all four `FORCE` it, which removes the owner's exemption: two rows visible before `FORCE`,
   zero after. — R4, R8.

3. **"And it says why, in a form an agent can act on."** `trappoint.explain_refusal` returns a
   structured reason set computed by the same engine that produced the refusal — because an
   explanation that can disagree with its refusal is worse than no explanation. On the demo's
   headline refusal it returns `not_computable` for the nearest admissible alternative and names
   the capability gap, rather than inventing a plausible answer. — R6.

**If there is room for a fourth, it is the negative one, and it is the most persuasive thing in
this domain.** `packages/trappoint-conformance/REFUSAL_DEPTH.md` is a *generated* file in which
the project measures its own architecture document's "the write fails twice over" sentence, finds
**depth 1 on 9 of 9 gated merge-gate histories**, and ships the number anyway with the
pre-committed response written next to it: *"cut the mechanism, do not ship it."* A submission
that publishes its own disconfirming measurement is making a claim about its other measurements
that no amount of assertion can make. — §4, `REFUSAL_DEPTH.md`.

---

## 7. WHAT THIS WORKER DID NOT DO

Stated so the orchestrator does not have to infer it.

* **No `terraform apply`, no redeploy, no AWS mutation, no SSM write, no credential printed or
  read.** The only network call was `curl` against the public demo origin — `GET /v1/health` and
  `POST /v1/demo/gate-run`, both unauthenticated, the second self-rolling-back with
  `persistence_check.identical: true`.
* **No grant widened.** The `materialise_checks` / `exposure_receipt` / `exposure_line` INSERT gap
  is open, documented in §3, and untouched. `GRANTS.yaml` was read and not edited.
* **No commit.** One file written: this one.
* **No ratchet, generator, or honesty document touched.** `HONESTY.md`, `CI-STATE.md`,
  `MUST-NOT-CLAIM.md` and `scripts/submission/capture_tool_evidence.py` were read only. No
  `continue-on-error`, no `|| true`, and `DEFAULT_MAX_RESPONSE_BYTES` was not approached.
* **Two scratch databases used and one dropped.** `w_w6_census` was created for the
  `GET DIAGNOSTICS` / `RETURNING … INTO` probe and dropped immediately. `w_w6` holds the
  `w6_force_demo` table from the `FORCE ROW LEVEL SECURITY` demonstration. `mainline_demo` was
  written to only by the schema-tier test suite, under its own private `site_id`; the seeded demo
  site still carries exactly one permit.
