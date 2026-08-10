<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# INTEGRATION & SEAM REPAIR — the plan, and what was measured before it

**Lead:** integration & seam-repair
**Date:** 2026-08-10
**Cluster:** local single node, `postgresql://root@127.0.0.1:26257/…?sslmode=disable`,
**CockroachDB CCL v26.2.5** (x86_64-pc-linux-gnu, built 2026/07/28, go1.25.5)
**Tree:** `verticals/mainline/db/migrations` — 261 files
**Scope:** make the chain apply 261/261 through the real runner, and make the product's
central claim demonstrable rather than asserted.

---

## 0 · VERDICT IN ONE LINE

> The repair set is **complete and measured**: quoting one identifier plus authoring
> **seven** tables (not five) takes the tree from **halted at file 79** to
> **268 objects applied, zero failures**. That was executed end to end before this plan was
> written. What remains unproven is not the schema — it is the **corpus wiring**, which
> reports `implemented 1 / 71` while seventy implementations sit on disk unimported, and
> the **gate proof**, which cannot run until both land.

---

## 1 · WHAT I MEASURED (not assumed)

Everything in this section was run against the live local node on 2026-08-10.

### 1.1 The real runner halts; it does not "fail 18 of 261"

```
$ trappoint migrate bootstrap --dsn …
bootstrapped: schema, schema_migration, schema_lock, schema_attestation, genesis attestation

$ trappoint migrate up --dsn … --tree mainline --migrations verticals/mainline/db/migrations
trappoint migrate: REFUSED: 0049z_meas_mutation_result: [42601] at or near "not": syntax error
```

The "243 of 261" figure in the brief comes from applying raw files with continue-on-error.
**`trappoint migrate up` is forward-only and stops at the first refusal**, which is
`0049z`, file **79 of 261**. Every downstream failure is therefore *invisible* to the
runner until the one above it is fixed. This is the single most important sequencing fact
in the wave: the repairs are discovered serially by the runner and must all land before
one green run exists.

### 1.2 The `family` error is a table-element parse collision, not a reserved word

`FAMILY` is **not** in `pg_get_keywords()`'s reserved set on v26.2.5 (I enumerated all 83:
`all analyse analyze and any array as asc … where window with` — no `family`). The caret in
the error lands on **`NOT`**, not on `family`:

```
  family            STRING NOT NULL,
                           ^
```

The parser read `family` as the **column-family table element** (`FAMILY name (cols)`),
took `STRING` as the family's name, and then wanted `(`. So the correct sweep is **not**
"reserved words"; it is *identifiers that collide with `CREATE TABLE` element keywords*
(`FAMILY`, `CONSTRAINT`, `PRIMARY`, `UNIQUE`, `CHECK`, `FOREIGN`, `INDEX`, `INVERTED`,
`LIKE`, `EXCLUDE`, `PARTITION`) **plus** the true reserved set anywhere.

**Sweep result, measured:** with `"family"` quoted, **every other file in the tree parses.**
There is no second collision on disk today. The lint rule W1 lands is therefore a
*forward* guard, and the seven new tables are exactly the place it earns its keep.

### 1.3 Class C is confirmed a bootstrap artefact, empirically

I pre-created schema `trappoint` before the continue-on-error pass. `0119a_fn_explain_refusal.sql`
then applied cleanly, and the failure count dropped from 18 to 17. **Class C is not a bug.**
The runner (`trappoint migrate bootstrap`, ruling D6) is the correct entry point; nothing is
to be "fixed" there, and W6 confirms it by driving the real runner rather than raw files.

### 1.4 There are SEVEN missing tables, not five

I enumerated every schema-qualified relation referenced in comment-stripped SQL across all
261 files and differenced it against every `CREATE TABLE` / `CREATE VIEW` in the tree. Two
tables the brief does not name are missing:

| table | referenced by | chain-blocking? |
|---|---|---|
| `mainline_ops.outbox` | `0101` (fn body), `0121` (trigger), `0198x` (comment) | **yes** |
| `mainline.identity_assignment` | `0140a` (fn body), `0145a` (trigger) | **yes** |
| `mainline.patrol_run` | `0163` | **yes** |
| `mainline_meas.agent_action` | `0164`, `0165`, `0166` | **yes** |
| `mainline_meas.standing` | `0171`, `0172`, `0187`–`0187e` | **yes** |
| **`mainline_meas.person_measure_policy`** | `0171` (JOIN), `0172` (JOIN) | **yes — undeclared in the brief** |
| **`mainline_ops.site_register_signal`** | `RLS-MATRIX.yaml` `rls_forbidden`, `test_mi_rls.py` | no — but the RLS test cannot pass without it |

`standing.policy_id` is `NOT NULL REFERENCES person_measure_policy (policy_id)`, so the two
must land together and in that order.

### 1.5 A measured platform fact that decides where each object may live

`CREATE FUNCTION` **does not resolve table references in a PL/pgSQL body** on v26.2.5:
`0140a_fn_cbm_account_guard` applied cleanly with `identity_assignment` absent. **`CREATE
TRIGGER` does** — `0145a` is where it failed. Consequence for the workers: a new table must
sort before the **trigger** that welds its consumer, not before the function.

### 1.6 The repair set is sufficient — proved, not projected

I applied the whole tree into a scratch database with `"family"` quoted and the seven
tables injected at their planned positions:

```
applied=268 failed=0
```

261 migration files + 7 tables, **zero failures**. Compare the same pass without the
repairs: `applied=244 failed=17`. The repair set is complete; nothing downstream is hiding.

### 1.7 The conformance corpus is wired shut

```
$ trappoint-conform --profile mainline --list
…
implemented 1 / 71
```

Seventy implementations exist in `packages/trappoint-conformance/cases/` (`cf02_…` …
`cf71_…`). I imported them directly and `implemented_case_ids()` returned **71**. The
runner never sees them because:

1. `cli.py` never calls `cases.load_all()`; and
2. `cases/` sits **outside** `src/` and is absent from
   `[tool.hatch.build.targets.wheel].packages`, so an installed environment cannot import it.

### 1.8 The corpus's world builder is shaped for the reference vertical, not MAINLINE

Running the corpus against the repaired schema aborts on the **first** case:

```
CF-02: building the LEGAL world failed at 'site'. … Cause: null value in column
"tenant_id" violates not-null constraint
```

`cases/_world.py::site_row()` inserts `(site_id, site_code, site_role)` only. MAINLINE's
`mainline.site` (0020a) additionally requires `tenant_id UUID NOT NULL` and
`taxonomy_ver INT4 NOT NULL`, and carries `CONSTRAINT site_code_is_lower_case
CHECK (site_code = lower(site_code))` — which the builder's `f"CONF-{…}"` also violates.
**Two defects on one line.** And `SetupRefused` is an `AssertionError`, which
`runner.run()` does not catch, so one unbuildable world **aborts the entire suite** instead
of reporting one `ERROR`.

### 1.9 The unwelding harness cannot be pointed at MAINLINE

`unweld/conftest.py` reads `TRAPPOINT_UNWELD_PROFILE` and resolves the schema from it, but
`mutable_cluster` hard-codes `tree = repo_root / REF_TREE`. `MAINLINE_TREE` is defined in
`container.py` and referenced only by a lint test. So the existing `REFUSAL_DEPTH.md` —
which honestly reports **depth 1** for every gated merge-gate history, measured on a
reference schema with **six stand-in relations** — has never been re-measured on the real
binding. That is the gap W9 closes.

### 1.10 Eleven further tables are named by GRANTS.yaml and created by nothing

`discordance_warrant`, `document_intake_finding`, `drift_finding`, `lesson`,
`merge_conflict`, `observed_assertion`, `propagation`, `resolution_memory`, `time_witness`,
`mainline_meas.assay_outcome`, `mainline_meas.external_attestation`.

**Out of scope for this wave, deliberately.** None is referenced by any migration, so none
blocks the chain; authoring eleven more tables would be a second domain's work smuggled
into a repair wave. W6 records the list from a real `grants apply --allow-missing` run so
the number is measured rather than remembered.

---

## 2 · DECISIONS

| # | Decision | Why, in one line |
|---|---|---|
| D1 | **Numbers come from what the consumers already cite**, not from a fresh reading of the allocation. | `0163`/`0164`/`0171`/`0187` headers say `requires: 0090 patrol_run`, `0089 agent_action`, `0089 standing`; GRANTS.yaml says `since: "0090"` / `"0099"` / `"0089"` — the numbers are already pre-committed in four places, and moving them would silently falsify all four. |
| D2 | Final allocation: `0049d` identity_assignment · `0089` agent_action · `0089a` person_measure_policy · `0089b` standing · `0090` patrol_run · `0099` outbox · `0099a` site_register_signal. | Every one lands in a band whose `mode = "authored"`, which is the only thing lint rule B enforces; ordering satisfies both the `standing → person_measure_policy` FK and §1.5's trigger rule. |
| D3 | The band owners named in `migrations.allocation.toml` for `0080-0089z` (recall) and `0090-0099z` (dm-periphery) **are not amended**. | `contents` is prose; `owner` is not machine-enforced; ARCHITECTURE.md §18 already places these exact objects in these exact bands. Editing the authority file to record a fact it already implies is churn with a collision risk. |
| D4 | Shapes are **transcribed** from ARCHITECTURE.md §5.7/§5.8/§5.9/§5.10 and from `tests/integration/algorithms/cbm/_pending_dependency.sql`, never invented. | A column a worker guessed at is a column the worker's own tests pass against and the deployment does not; §5 is verbatim DDL and the CBM stand-in is verbatim from `workers.json`. |
| D5 | Each new evidentiary table gets its **append-only weld** in the same wave (`0145f`, `0149a`) using the existing `mainline.fn_refuse_mutation()`. | MI01 is cited by the very views that consume these tables (`0164`: "`agent_action` is one of them"); a table that arrives unweled arrives with its invariant already broken. |
| D6 | The `family` fix is `"family"` (quote), **not** a rename. | `mainline_meas.mutation_result.family` is named in `docs/leads/algorithms.md` and in the mutation-ratchet code path; renaming a column to dodge a parser is a wider blast radius than two quote characters. |
| D7 | The keyword sweep ships as a **lint rule**, not as a one-off grep. | The tree is clean today (§1.2); the seven new tables are precisely the moment a second collision could enter, and a convention cannot hold that — a lint can (`lint.py`'s own words). |
| D8 | **No claim of refusal depth ≥ 2 is made in advance.** W8 and W9 measure and report what they observe. | `REFUSAL_DEPTH.md` already records, honestly, that the gated histories measured **depth 1** for a *structural* reason: `fn_permit_merge_gate` deliberately declines to decide when the counter agrees, so the named constraint keeps the exhibit. A truthful red beats a fabricated green, and pre-committing to a number is how a measurement becomes a formality. |
| D9 | The gate proof is written **standalone**, not on top of `cases/_world.py`. | W7 is editing that file in the same wave; more importantly an independent second implementation of the same history is better evidence than a second caller of the same builder. |
| D10 | Nobody edits a conformance **case** implementation this wave. | The wave's deliverable is *the chain applies* and *the gate refuses*, plus an honest corpus census. A worker who may edit cases is a worker who can make the census green by editing it. |
| D11 | Each worker uses its **own database** on the shared local node (`repair_w<N>`), created and dropped by itself. | Ten workers doing DDL against one `defaultdb` would interleave; a database per worker costs nothing on a single node and makes every run reproducible in isolation. |
| D12 | The eleven GRANTS-only tables (§1.10) are **reported, not authored**. | Scope discipline: they block no migration, and eleven speculative tables would be a bigger, less reviewable diff than the seam this wave exists to close. |

---

## 3 · SEQUENCING

```
        ┌── W1 family + keyword lint ──┐
        ├── W2 identity_assignment ────┤
  wave A├── W3 agent_action ───────────┤ (fully parallel — disjoint files, disjoint DBs)
        ├── W4 policy + standing ──────┤
        └── W5 patrol_run/outbox/srs ──┘
                     │
                     ▼
  wave B      W6 chain drive 261/261, lock, MIGRATIONS.md, grants census
                     │              W7 corpus wiring (parallel with W6 — no shared file)
                     ▼                       │
  wave C      W8 THE GATE PROOF ◄────────────┤
              W9 unwelding matrix on MAINLINE┤
              W10 corpus census + just recipes
```

W1–W5 and W7 can all start immediately; W7's work does not touch the migration tree.
W6 needs W1–W5. W8, W9, W10 need W6; W9 and W10 additionally need W7.

---

## 4 · THE TEN WORKERS

| id | title | owns |
|---|---|---|
| W1 | `family` fix + reserved/element-keyword lint rule | `0049z`, `keywords.py`, `lint.py`, `test_keywords.py` |
| W2 | `mainline.identity_assignment` + append-only weld | `0049d`, `0145f` |
| W3 | `mainline_meas.agent_action` + append-only weld | `0089`, `0149a` |
| W4 | `person_measure_policy` + `standing` | `0089a`, `0089b` |
| W5 | `patrol_run`, `outbox`, `site_register_signal` | `0090`, `0099`, `0099a` |
| W6 | drive the real runner to 261/261; lock; manifest; grants census | `migrations.lock.json`, `MIGRATIONS.md`, evidence + report |
| W7 | conformance corpus wiring + MAINLINE-shaped world builder | `cli.py`, `runner.py`, `pyproject.toml`, `cases/_world.py` |
| W8 | **THE GATE PROOF** | `tests/integration/gate/*`, `evidence/gate-refusal-proof.json`, `docs/proof/merge-gate-refusal.md` |
| W9 | unwelding matrix re-measured on MAINLINE | `unweld/conftest.py`, `unweld/container.py`, `REFUSAL_DEPTH-MAINLINE.md` |
| W10 | conformance census on MAINLINE + `just` recipes | `justfile`, `scripts/run_conformance_mainline.py`, evidence + report |

Full briefs are carried in the dispatch payload. File ownership is literal and disjoint;
anything a worker needs that it does not own goes under `cross_domain_notes`.

---

## 5 · WHAT WOULD MAKE THIS WAVE A FAILURE

1. A green chain that nobody drove through `trappoint migrate up` — raw-file application is
   not the runner and does not write the attestation chain.
2. A gate proof that reports a SQLSTATE without the **constraint name**. `23514` alone is a
   number; `23514 gate_closed_when_issued` is an exhibit.
3. Any claim of refusal depth that was not observed by removing a mechanism and re-running
   the identical history.
4. A conformance census that counts a `SKIPPED` or a `PENDING` as a pass.
5. A new table whose columns were convenient rather than transcribed.
