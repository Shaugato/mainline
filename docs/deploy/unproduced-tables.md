<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# THE UNPRODUCED TABLES — the gap was six, and the chain is now 271/271

**Worker** `w1-unproduced-tables` (domain: deploy) · **Date** 2026-08-10
**Evidence** [`evidence/deploy/chain-261.json`](../../evidence/deploy/chain-261.json)

---

## 0. The headline, and the correction that comes with it

The migration chain applies **in full**. Measured twice in succession, against the pinned
local node, into a throwaway database, file by file, continuing past failures so that
`failed` is a census of the whole stream and not the first place it stopped:

```
files=271 applied=271 failed=0 retried=0 wall=46.35s
```

Three numbers in that line are not the numbers this worker was briefed with, and the
difference is the substance of this document.

| | Briefed | Measured today | Why |
|---|---|---|---|
| Files in the tree | 261 | **271** | A parallel wave landed ten files (§2) |
| Applied | 246 | **271** | The six producers exist |
| Tables with no producer | 6 | **0** | — |

**This worker wrote no SQL.** Every one of the six `CREATE TABLE` migrations it was
briefed to author already existed on disk when it started, delivered by the
producer-completion wave documented in `docs/leads/producers-plan.md`. Writing them again
would have been destructive, and §3 measures exactly how destructive. The work that
remained was verification, the derived lock manifest, and this record.

The file is still called `chain-261.json` because that is the path this worker was
granted and a worker does not rename its own deliverables. Its `files` field says 271.
**Trust the field, not the filename.**

---

## 1. The gap was SIX, and the sixth was found by reading consumers

`docs/HONESTY.md` and `scripts/proof/gate_refusal.py` both enumerate **five** relations
with consumers and no producer:

```
mainline_ops.outbox
mainline.identity_assignment
mainline.patrol_run
mainline_meas.agent_action
mainline_meas.standing
```

There is a sixth: **`mainline_meas.person_measure_policy`**.

### How it was found

Not by reading the enumeration — the enumeration is what was wrong. By reading the
*consumers*, which is a different question and a strictly stronger one. The enumeration
answers "which tables did somebody notice were missing"; the consumer census answers
"which relations does a statement in this tree resolve, and does a `CREATE TABLE` for it
exist anywhere". Only the second is checkable by a machine.

```
grep -rn "person_measure_policy" verticals/mainline/db/migrations/*.sql
  → 0171, 0172, 0187d reference it; 0170 documents it
grep -rl "CREATE TABLE.*person_measure_policy" verticals/mainline/db/migrations/
  → nothing, anywhere in the repository
```

### Why missing it would have cost nothing visible, and everything real

The count of *failing migrations* is 15 either way, which is precisely why the fifth-vs-sixth
error survived. `mainline_meas.standing.policy_id` is `NOT NULL` and carries a foreign key
into `mainline_meas.person_measure_policy`.
Create `standing` alone and the `42P01` does not go away — it **moves one file along**,
from `0171` to `0089b` itself. The failure count is stable under the wrong fix, so the
failure count could never have told anyone the fix was wrong. Nothing but reading the
FK target would. On the live schema the constraint reads:

```
policy_id UUID NOT NULL,
CONSTRAINT fk_policy FOREIGN KEY (policy_id)
  REFERENCES mainline_meas.person_measure_policy(policy_id)
```

`0171_v_standing_components.sql` states the dependency in its own header, and its body
proves it — the view is a `JOIN` across both tables:

```sql
FROM mainline_meas.standing st
JOIN mainline_meas.person_measure_policy pmp
  ON pmp.policy_id = st.policy_id
```

**This is now enforced rather than remembered.** `trappoint migrate lint` grew a rule D,
a whole-tree producer-existence census (`packages/trappoint-migrate/src/trappoint_migrate/producers.py`,
`--no-producers` to skip). A relation with consumers and no `CREATE` applies clean until
the first statement that resolves it and then halts a forward-only chain; the census finds
it without a cluster. The class of bug that cost 105 unreachable files is now a lint
finding.

---

## 2. The six producers, and the consumer that dictated each

All six were on disk, untracked, when this worker began. Numbers come from the consumers'
own `requires:` lines and from `verticals/mainline/db/migrations.allocation.toml`, whose
`mode` field `trappoint migrate lint` rule B enforces. None was invented.

| # | Relation | Producer | Dictated by |
|---|---|---|---|
| 1 | `mainline.identity_assignment` | `0049d_identity_assignment.sql` | `0140a_fn_cbm_account_guard.sql`, `0145a_trg_cbm_account_guard.sql` |
| 2 | `mainline_meas.agent_action` | `0089_agent_action.sql` | `0164_v_agent_actions`, `0165_v_gate_latency_daily`, `0166_v_txn_restart_daily` |
| 3 | `mainline_meas.person_measure_policy` | `0089a_person_measure_policy.sql` | `0171`, `0172`, `0187d`; documented by `0170_v_disposition_profile` |
| 4 | `mainline_meas.standing` | `0089b_standing.sql` | `0171`, `0172`, `0187`, `0187a`–`0187e` |
| 5 | `mainline.patrol_run` | `0090_patrol_run.sql` | `0163_v_fixity_coverage` |
| 6 | `mainline_ops.outbox` | `0099_outbox.sql` | `0101` line 91, `0121`, `0168`, `0198x` |

A seventh file, `0099a_site_register_signal.sql`, and three append-only welds
(`0145f`, `0149a`, `0149b`) landed with them. `mainline_ops.outbox` deliberately gets **no**
weld: it is the one TTL table in `mainline_ops`, and a `BEFORE DELETE` refusal trigger
would make row expiry fail forever (producers-plan D5).

### 2.1 `0049d`, not `0049b` — the number in the brief was already taken

Two files written before the producer say `0049b` in prose: `0049c_cbm_account.sql`'s band
note and `0140a_fn_cbm_account_guard.sql`'s `requires:` line, both authored when `0049b`
was unclaimed. It was claimed in the interim by `0049b_commutation_edge.sql`, which is
committed. The producer therefore took the next free letter in the same authored band,
`0049d`, and `migrations.allocation.toml` was restated to name it. The stale citations
belong to files nobody in this wave owned and were reported rather than edited.

**This worker was briefed to create `0049b_identity_assignment.sql`. Doing so would have
put a second table in an occupied slot.**

### 2.2 `mainline.patrol_run` — seven columns, and the view fixes every type

`0163_v_fixity_coverage` is the whole specification. It selects `site_id`, `patrol_class`,
`started_at`, `finished_at`, `n_in_scope`, `n_checked`, `n_not_checked`, and its
*aggregates* fix the types more tightly than the select list does:

```sql
count(*) FILTER (WHERE pr.finished_at IS NULL)  -- finished_at must be NULLABLE
count(*) FILTER (WHERE pr.n_in_scope = 0)       -- integral, comparable to 0
sum(pr.n_not_checked)::NUMERIC
  / nullif(sum(pr.n_in_scope), 0)::NUMERIC      -- summable; zero must be reachable
WHERE pr.started_at > now() - INTERVAL '90 days' -- started_at is TIMESTAMPTZ
```

`finished_at` being nullable is not a modelling preference — it is the only reading under
which `unfinished_runs` can ever be non-zero. Live shape confirms 12 columns; the seven
the view names are present with types that make each aggregate legal, which is proved by
the view *executing*, not merely existing (§4).

### 2.3 `mainline_meas.agent_action` — the aggregates are the type system

Three views read it, and between them they pin nearly every column:

- `0165` groups on `date_trunc('day', a.at)` → `at` is `TIMESTAMPTZ`; filters
  `a.outcome IN ('ok','refused','error','abstained')`; takes `min`/`avg`/`max` of
  `a.latency_ms` and compares it to `250`/`1000`/`5000` → numeric and **nullable**
  (`count(*) FILTER (WHERE a.latency_ms IS NULL) AS unmeasured` is a column of the view).
- `0166` filters `a.sqlstate` against `'40001'`, `'23514'`, `'23503'`, `'23505'`,
  `'P0001'`, `'42501'` → five-character `STRING`, not an integer.
- `0165` filters `WHERE a.agent_role = 'agent_gate'` and groups by `a.tool`; `0166` groups
  by `a.agent_role`. Both treat it as a comparable, groupable scalar.

Live shape: 15 columns, `at`/`agent_role`/`tool`/`outcome`/`sqlstate`/`latency_ms` all
present.

### 2.4 `mainline_ops.outbox` — the comment in `0198x` is the specification

`0198x_no_rls_on_cdc_sources.sql` is a `COMMENT ON TABLE` stating binding platform law.
Every clause of it is honoured, and each was verified against the **live** schema rather
than the file:

| Law | Verified |
|---|---|
| **No row-level security** | `pg_class.relrowsecurity = false`, `relforcerowsecurity = false`; `pg_policies` count for schema `mainline_ops` = **0** |
| **Single column family** | `SHOW CREATE TABLE` contains no `FAMILY` clause → one implicit family |
| **Row-level TTL, 30 days** | `WITH (ttl = 'on', ttl_expiration_expression = 'expires_at')`, `expires_at DEFAULT now() + '30 days'`; the only TTL table in the schema |
| **Pointers and digests only** | `payload JSONB NOT NULL`; `0101` writes `'{}'::JSONB` and passes ids and a severity, never clause or narrative text |

CDC queries fail on RLS tables *and* on multi-family tables on v26.2, so both are outage
avoidance and not preference. `FAMILY` is a reserved keyword repo-wide and appears as no
bare column name.

The insert that `0101_fn_check_materialised` performs is satisfied exactly:

```sql
INSERT INTO mainline_ops.outbox (kind, subject_id, site_id, max_severity, payload)
     VALUES ('check_opened', (NEW).check_id, (NEW).site_id, (NEW).severity, '{}'::JSONB);
```

All five named columns exist; the six unnamed ones (`signal_id`, `target_site`,
`activity_root`, `score`, `emitted_at`, `expires_at`) are nullable or defaulted, so the
insert is legal as written. `signal_id` defaults to `gen_random_uuid()` — **no sequence,
no `nextval`, no `SERIAL`, no `unique_rowid()`**, all four banned repo-wide and all four
confirmed absent by lint.

---

## 3. Why this worker wrote no SQL — measured, not asserted

The brief named six paths that do not exist and are not the paths the producers occupy:
`0049b_identity_assignment.sql`, `0089_meas_agent_action.sql`,
`0089a_meas_person_measure_policy.sql`, `0089b_meas_standing.sql`, `0099_ops_outbox.sql`
(and `0090_patrol_run.sql`, which *is* the delivered path and is correct as it stands).

Creating them would not have produced duplicate *versions* — discovery keys on the whole
filename stem, so `0089_agent_action` and `0089_meas_agent_action` are two versions and
the tree would still be legal. It would have produced duplicate **relations**, and the
second `CREATE TABLE` for a relation is refused:

```
second CREATE TABLE refused: [42P07] relation
  "w_w1_dupe_test.mainline_meas.agent_action" already exists
```

Five of the six briefed paths are new files (`0090_patrol_run.sql` is already the delivered
path). Each duplicates a relation that a lower-sorting file has already created, so each
fails: the tree becomes **276 files with 5 failures**, a green chain turned red, plus a
second table dropped into the occupied `0049b` slot. **The correct action on a task
already done is to verify it and say so, not to do it again.** Every claim above is a
measurement against the delivered files.

---

## 4. What was actually verified

Against the pinned local node — Docker `mainline-crdb`, `cockroachdb/cockroach:v26.2.5`,
`postgresql://root@127.0.0.1:26257` — into throwaway database `w_w1_unproduced_tables`,

> **ANNOTATED 2026-08-14 — the container name still resolves, but the port no longer reaches
> it.** `mainline-crdb` exists on TRAPPOINT and is `Exited`; the node answering
> `127.0.0.1:26257` today is a **different** container, `trappoint-crdb` (same image,
> `cockroachdb/cockroach:v26.2.5`). The results below are not withdrawn — they were taken
> against the named node and the image is identical — but **anyone re-running this section
> by pointing at the DSN alone will be measuring a different container than the one this
> section names**, and would not be told. Confirm with
> `docker ps --format '{{.Names}}\t{{.Image}}'` before treating a re-run as a reproduction;
> the `gc.ttlseconds = 4500` pin below is a property of the database, not of the container,
> and must be re-asserted on whichever node is actually answering.

with `gc.ttlseconds` pinned to **4500**, the value Cloud Basic enforces, so a local pass is
not a pass under a more permissive setting.

| Check | Result |
|---|---|
| `trappoint migrate lint` (headers, sequence ban, invariant citation, band/mode, producer census) | **0 findings**, 411 files |
| Whole chain, file by file, continuing past failures | **271/271 applied, 0 failed**, twice |
| Files needing a `40001` retry | 0 (single-node; the loop is present and reports honestly) |
| `trappoint migrate lock` | `migrations.lock.json is current` |
| `scripts/proof/gate_refusal.py` | **VERDICT PROVEN**, exit 0, `chain.failed_count = 0` |
| All six relations present with the consumers' columns | yes — see `producer_relations` in the evidence |
| All 8 consumer views `SELECT`-able | yes |

The view check is the load-bearing one. A view whose base table has an incompatible column
type fails at `CREATE`; a view whose *aggregate* is illegal fails when the plan binds. All
eight were executed, not merely looked up in the catalogue:

```
mainline_audit.v_fixity_coverage      mainline_audit.v_changefeed_health
mainline_audit.v_agent_actions        mainline_qa.v_standing_components
mainline_audit.v_gate_latency_daily   mainline_qa.v_my_record
mainline_audit.v_txn_restart_daily    mainline_qa.v_disposition_profile
```

Resulting schema: **86 base tables, 20 views** across the five schemas. RLS is on **and
forced** on `mainline_meas.standing` with all four policies from `0187b`–`0187e`; RLS is
absent from every table in `mainline_ops`, as `0198x` requires.

The single slowest file is `0180_disposition_peer_visible.sql` at 1.50 s — the same file
the lead measured slowest on Cloud, at 7.3 s. That the two runs agree on *which* file is
slowest, five times apart in absolute terms, is the useful part.

### 4.1 One failure that was the probe's fault, and is recorded because it was

The first run reported 270/271. The failure was `0119a_fn_explain_refusal`, `3F000`:

```
cannot create "trappoint.explain_refusal" because the target database
or schema does not exist
```

The `trappoint` bookkeeping schema sits **outside** the numbered sequence by ruling D6 and
is created by `trappoint migrate bootstrap`. The probe had not run it. That is a defect in
the measurement, not in the chain, and the fix was to bootstrap first — as the real runner
always does. It is written down here because a green number whose first attempt was red is
worth less if the red is quietly dropped.

---

## 5. The lock manifest was stale, for an unrelated reason

`verticals/mainline/db/migrations.lock.json` is marked `GENERATED — DO NOT EDIT BY HAND`.
It was regenerated with the committed generator, `trappoint migrate lock --write`:

```
wrote verticals\mainline\db\migrations.lock.json — 271 file(s),
      107 rendered, 164 authored, 30 counsel-gated
```

Ten of the eleven staleness findings were the new files. The eleventh was not:

```
! 0049z_meas_mutation_result.sql: manifest says sha256='1d993f87…',
                                  the tree says 'b18fee0d…'
```

`git log` places the last lock regeneration at `904f1b4` and the last edit to
`0049z_meas_mutation_result.sql` at `c76c454`, which is later, and `git diff HEAD` on that
file is empty. **The committed lock has therefore disagreed with the committed tree since
`c76c454`** — a pre-existing drift, not one this wave caused, and now closed.

---

## 6. Still open — not this worker's files

Two committed artefacts still carry the pre-wave numbers and neither is owned here:

1. **`docs/HONESTY.md`** publishes `261` files, `246` applied, and a count of `5`
   unproduced tables, each sourced to `evidence/gate-refusal/proof-20260809T213857Z.json`.
   All three are now false in the *useful* direction. The page should be **extended with
   the new measurement, not quietly corrected** — the method that found the sixth table is
   the method the page itself recommends, and that is worth saying out loud.
2. **`scripts/proof/gate_refusal.py`** hard-codes `UNPRODUCED_TABLES` as a five-tuple and
   carries prose asserting that `0121_trg_check_materialised.sql` "could not apply". The
   script still exits 0 and still prints `VERDICT PROVEN`, because it reports the
   enumeration rather than depending on it — but the enumeration is now empty in fact and
   five-long in the source, and a constant that no longer describes the tree is a trap for
   the next reader.

Neither blocks the deploy domain. Both should be closed before submission, because the
repository's own claim is that its honesty page is its best feature, and a stale honesty
page is the one defect the product cannot afford.
