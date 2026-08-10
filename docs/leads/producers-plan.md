<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# PRODUCER COMPLETION — closing the consumer/producer seam, and demonstrating the suite

**Lead:** producer-completion
**Date:** 2026-08-10
**Cluster:** `mainline-crdb`, local single node, `postgresql://root@localhost:26257/…?sslmode=disable`,
**CockroachDB CCL v26.2.5** (x86_64-pc-linux-gnu, built 2026/07/28 18:56:00, go1.25.5)
**Tree:** `verticals/mainline/db/migrations` — 261 files today, 268 when this wave lands
**Scope:** 261/261 through the *deployment* runner · the conformance suite executed to completion ·
the gate proof's `open_blocking` caveat retired · `docs/HONESTY.md` re-based on the new numbers.

---

## 0 · THE VERDICT, AND THE NUMBER THAT CHANGES

> The headline in `docs/HONESTY.md` — **"246 of 261 applied"** — is a *census* number produced by
> a continue-on-error pass. Through `trappoint migrate up`, the runner a deployment actually
> uses, the tree applies **155 of 261** and then stops dead. I ran it. It is not a subtlety;
> it is a different claim, and the smaller number is the true one.

```
$ trappoint migrate bootstrap --dsn postgresql://root@localhost:26257/lead_probe?sslmode=disable
bootstrapped: schema, schema_migration, schema_lock, schema_attestation, genesis attestation

$ trappoint migrate up --dsn … --tree mainline --migrations verticals/mainline/db/migrations
trappoint migrate: REFUSED: 0121_trg_check_materialised: [42P01] relation "mainline_ops.outbox" does not exist

$ SELECT count(*) FROM trappoint.schema_migration;
156                                      -- 155 clean + 0121 left DIRTY
```

`0121_trg_check_materialised.sql` is **file 156 of 261** in apply order. Everything after it is
invisible to the runner: forward-only means the 105 files below the halt have never been
executed by the thing that will execute them in production. The proof script's 246/261 comes
from its own continue-on-error chain (it says so in its docstring), and both numbers are honest
about *what they measured* — but only one of them describes a deployment.

**Therefore the wave's exit condition is not "246 becomes 261". It is "155 becomes 268, through
`trappoint migrate up`, in one uninterrupted forward-only run, with an attestation row per
file."**

---

## 1 · WHAT I MEASURED, MYSELF, TODAY

### 1.1 There are SEVEN tables with no producer, not five

The brief names five. I differenced every schema-qualified relation referenced in
comment-stripped SQL across the tree against every `CREATE TABLE`/`CREATE VIEW` in it, and
cross-checked against the failure classification in
`evidence/gate-refusal/proof-20260810T004200Z.json`. Two more are missing, and the first of them
is chain-blocking:

| relation | named by | why the census missed it |
|---|---|---|
| `mainline_ops.outbox` | `0101` (fn body), `0121` (trigger), `0198x` (comment) | — |
| `mainline.identity_assignment` | `0140a` (fn body), `0145a` (trigger) | — |
| `mainline.patrol_run` | `0163` | — |
| `mainline_meas.agent_action` | `0164`, `0165`, `0166` | — |
| `mainline_meas.standing` | `0171`, `0172`, `0187`–`0187e` | — |
| **`mainline_meas.person_measure_policy`** | `0171` and `0172` — both `JOIN` it, and `standing.policy_id` is `NOT NULL REFERENCES` it | CockroachDB reports the **first** absent relation in a statement. `standing` is named first in both views, so `person_measure_policy` never appeared in a SQLSTATE. It is a *shadowed* gap, and a census that counted SQLSTATEs could not have seen it. |
| **`mainline_ops.site_register_signal`** | `RLS-MATRIX.yaml` `rls_forbidden`, `test_mi_rls.py::test_site_register_signal_has_no_row_level_security` | Blocks no migration. Blocks the RLS negative assertion, which is scope item (c). |

This is confirmed independently: the prior integration-repair lead reached the same seven
(`docs/leads/integration-repair.md` §1.4) and applied them into a scratch database to
`applied=268 failed=0`. That plan was written; **its migration files were never authored** —
`ls verticals/mainline/db/migrations | wc -l` is still 261 and the runner still halts at 0121.
This wave executes it.

### 1.2 The contracts are transcription, not invention — and the sources are exact

Not one of the seven needs to be guessed at. Every column, type, key and CHECK is written down
somewhere that already binds:

| table | authoritative source |
|---|---|
| `mainline_meas.agent_action` | `hackathon-research/ARCHITECTURE.md` §5.7, line 1517 — verbatim DDL, and `0164`/`0165`/`0166` select exactly its columns (`agent_role, tool, outcome, at, transport, sqlstate, model_id, prompt_version, latency_ms`) |
| `mainline_meas.person_measure_policy` | ARCHITECTURE.md §5.7 line 1543 — verbatim, including `notice_precedes_effect` and `instrument_precedes_effect` |
| `mainline_meas.standing` | ARCHITECTURE.md §5.7 line 1561 — verbatim, including `PRIMARY KEY (actor_sub, hazard_class, window_from)` and `CONSTRAINT within_policy` |
| `mainline.patrol_run` | ARCHITECTURE.md §5.8 line 1629 — verbatim; `0163` reads `site_id, patrol_class, finished_at, n_in_scope, n_checked, n_not_checked, started_at` |
| `mainline_ops.outbox` | ARCHITECTURE.md §5.10 line 1843 — verbatim, single-family, TTL 30 d; `0101`'s body inserts `(kind, subject_id, site_id, max_severity, payload)` |
| `mainline_ops.site_register_signal` | ARCHITECTURE.md §5.9 line 1266 — verbatim |
| `mainline.identity_assignment` | `docs/leads/workers.json` (algorithms/margin-assignment brief item 6), transcribed into `tests/integration/algorithms/cbm/_pending_dependency.sql`; the *consumer* `0140a_fn_cbm_account_guard` reads `g.ancestor_clause_uuid`, `g.commit_id`, `g.relation IN ('split','merge','matched')`, and `tests/integration/algorithms/cbm/_cbm_sql_support.py::insert_assignment` writes exactly `(site_id, commit_id, ancestor_clause_uuid, descendant_clause_uuid, relation, stage, score, margin, policy_sha256, computed_by)` with `relation = 'absent'` exercised by `test_balance_refusal.py` |

**The `identity_assignment` case is the one that has a live acceptance test already written.**
`_cbm_sql_support.stood_in_objects()` resolves each stand-in against the real tree *by content*;
`full_stack()` drops `_pending_dependency.sql` from the apply stack the moment a real migration
creates the table. So the entire `tests/integration/algorithms/cbm/` suite — balance refusal,
generation monotonicity, the ungated differential — re-runs against the *real* DDL with no edit
to a single test file. If the authored table does not satisfy its consumers, that suite goes red
immediately. That is the seam-failure detector, and it is free.

### 1.3 The numbers are pre-committed in four places, so they are not mine to choose

`0163`'s header says `requires: 0090 mainline.patrol_run`. `0164`/`0165`/`0166` say
`requires: 0089 mainline_meas.agent_action`. `0171`/`0172` say
`requires: 0089 mainline_meas.standing · 0089 mainline_meas.person_measure_policy`. `0198x` says
`requires: 0099 mainline_ops.outbox`. `GRANTS.yaml` carries `since: "0090"` on
`mainline.patrol_run`, `since: "0099"` on `mainline_ops.outbox` (three rows) and `since: "0089"`
on `mainline_meas.standing`. ARCHITECTURE.md §18 places `agent_action, person_measure_policy,
standing` in `0080-0089` and `outbox, site_register_signal` in `0099`.

Choosing different numbers would silently falsify four committed artefacts. The allocation is
therefore:

```
0049d  mainline.identity_assignment          band 0049a-0049z   authored   (algorithms annexe)
0089   mainline_meas.agent_action            band 0080-0089z    authored
0089a  mainline_meas.person_measure_policy   band 0080-0089z    authored
0089b  mainline_meas.standing                band 0080-0089z    authored   (FK -> 0089a)
0090   mainline.patrol_run                   band 0090-0099z    authored
0099   mainline_ops.outbox                   band 0090-0099z    authored
0099a  mainline_ops.site_register_signal     band 0090-0099z    authored
0145f  trg identity_assignment append-only   band 0145-0149z    authored
0149a  trg agent_action append-only          band 0145-0149z    authored
0149b  trg person_measure_policy append-only band 0145-0149z    authored
```

### 1.4 What the lint actually enforces, measured against the source

`_rule_b_allocation` in `packages/trappoint-migrate/src/trappoint_migrate/lint.py` resolves a
filename's allocation key to a band and compares **mode** — `rendered` vs `authored` vs
`unallocated`. It does **not** compare owner; `owner` and `contents` are prose the file carries
for a human. Every number above lands in a band whose `mode = "authored"`, so lint rule B admits
them as written, and `trappoint migrate lint --root verticals/mainline/db/migrations` reports
**no findings** on the tree today (measured).

That is not a licence to land files under an owner string that does not name them. **W1 extends
the `contents` prose of the three affected bands to enumerate the new files, and changes nothing
else** — no `first`, no `last`, no `owner`, no `mode`, so the exhaustive-and-disjoint assertion in
`packages/trappoint-migrate/tests/test_allocation.py` cannot move. Extending the authority's
description of what it already grants is the deliberate act the brief asks for; carving a new
band would be a change with a collision risk and no benefit.

### 1.5 A measured platform fact that fixes the ordering

`CREATE FUNCTION` does **not** resolve table references inside a PL/pgSQL body on v26.2.5 —
`0140a_fn_cbm_account_guard` and `0101_fn_check_materialised` both applied cleanly with their
tables absent. `CREATE TRIGGER` **does** — `0121` and `0145a` are exactly where the tree failed.
Consequence: a new table must sort before the **trigger** that welds its consumer, never before
the function. `0049d < 0145a` ✓ · `0099 < 0121` ✓.

### 1.6 The runner is slow, and the wave has to budget for it

`trappoint migrate up` with the default `--attest each` took **≈15 minutes to reach file 156**
(≈5.8 s/file — it recomputes a schema fingerprint after every statement, over a schema that is
growing). A full 268-file run is a **25–30 minute** operation. Iterate with `--attest final`;
take the record run with `--attest each`. Budget it, do not discover it.

A failed run leaves the version **DIRTY** (`schema_migration` carried 156 rows with `0121`
present after a halt). The clean recovery in a wave like this is a **fresh database per attempt**,
not `trappoint migrate force`.

### 1.7 The conformance suite: the corpus is alive, the runner cannot see it

```
$ trappoint-conform --profile mainline --list
… implemented 1 / 71

$ cd packages/trappoint-conformance && python -c "import cases; print(len(cases.load_all()))"
71
```

Seventy-one implementations exist and import cleanly. Four defects stand between that and a
demonstrated suite, and each is small:

1. **`cli.py` never calls `cases.load_all()`.** Seventy cases report `PENDING` because nothing
   imported them.
2. **`cases/` sits outside `src/`** and is absent from `[tool.hatch.build.targets.wheel].packages`,
   so an installed environment cannot import it at all — it only worked above because I `cd`'d
   into the package directory.
3. **`SetupRefused` is an `AssertionError`,** and `runner.run()` catches only `psycopg.Error`. One
   unbuildable world therefore **aborts the whole suite** instead of reporting one result. This is
   why the census records 182 *errors* rather than 182 reports.
4. **`cases/_world.py::site_row()` is shaped for the reference vertical.** It inserts
   `(site_id, site_code, site_role)`; `mainline.site` (0020a) additionally requires
   `tenant_id UUID NOT NULL` and `taxonomy_ver INT4 NOT NULL`, and carries
   `CHECK (site_code = lower(site_code))` which the builder's `f"CONF-{…}"` violates. It also
   writes the literal `site_role = 'conf_role'` for every case against
   `CONSTRAINT site_role_unique`, so with `ON CONFLICT DO NOTHING` the *second* case's site row
   is silently not inserted — a defect that only appears once the first one is fixed.

And a fifth thing that is not a defect but decides the shape of the report: **22 cases carry a
`requires` capability token** (`mainline.propagation`, `role:mainline_auditor`,
`policy:mainline.permit`, …). Today the CLI only marks a token satisfied when a human passes
`--requires`, so every one of those cases would report `SKIPPED` against a fully migrated
cluster. The honest fix is to **probe the live database** for each token and report
`CANNOT RUN — <token> does not exist` with the object named. Six of those tokens name relations
that this wave deliberately does not author (`propagation`, `observed_assertion`,
`merge_conflict`, `frontier_move`, `discordance_warrant`, `coverage_certificate`); those six
cases will be published as cannot-run with their reason, which is the truthful result and is
worth more than a green produced by lowering the bar.

### 1.8 The gate proof retires its own caveat, and can be made stronger than that

`scripts/proof/gate_refusal.py` already probes for the `check_materialised` trigger
(`history.projection_trigger_present`) and only writes `open_blocking` itself when the trigger is
absent. So the moment `0099` and `0121` apply, the caveat **disappears on its own**. That is
necessary and not sufficient. The materially stronger artefact is to *prove the trigger did the
work*: read back the `mainline_ops.outbox` row the trigger emitted (`kind = 'check_opened'`,
`subject_id = check_id`), record the `gate_epoch` before and after, and assert
`counter_source == "trigger check_materialised -> mainline.fn_check_materialised"` rather than
merely reporting it. Then the sentence is not "the gate refused" but **"the trigger projected the
counter, emitted the CDC signal, bumped the epoch, and the gate refused"** — and every clause of
it is a value in the JSON.

`UNPRODUCED_TABLES` must also shrink to `()`. It is not cosmetic: the script classifies a failure
as *explained* only if it is attributable to a listed table, so an empty tuple turns any residual
failure into `chain.failures_unexplained`, which is a hard NOT PROVEN. That is the correct
ratchet.

---

## 2 · DECISIONS

| # | Decision | Why, in one line |
|---|---|---|
| **D1** | **Seven tables, not five**, and the plan says so in the first section. | `person_measure_policy` is a `NOT NULL REFERENCES` target of `standing` and a `JOIN` in two views; the chain cannot reach 268 without it, and it was invisible only because CockroachDB names the first absent relation. |
| **D2** | Numbers come from what the consumers already cite, not from a fresh reading of the allocation. | Four committed artefacts (`requires:` headers, `GRANTS.yaml since:`, ARCHITECTURE §18, `RLS-MATRIX.yaml`) already fix them; moving one falsifies all four. |
| **D3** | The allocation table is extended in **prose only** — `contents` restated on three bands, `first`/`last`/`owner`/`mode` untouched. | Rule B enforces mode; exhaustive-and-disjoint is asserted by a test. Carving a band buys nothing and risks the one invariant the file exists to hold. Recorded here so it is a decision, not a slip. |
| **D4** | Every shape is **transcribed** from ARCHITECTURE.md §5.7/§5.8/§5.9/§5.10 or from the consumer that reads it, and each new file cites the line it came from. | A column a worker guessed is a column that worker's tests pass against and the deployment does not. |
| **D5** | **`mainline_ops.outbox` gets NO append-only weld, and this is load-bearing.** | It is the one TTL table in `mainline_ops` (30 days, allowlist entry 1 of 3). A `BEFORE DELETE` refusal trigger would make the TTL job fail forever. `agent_action`, `identity_assignment` and `person_measure_policy` DO get welds — MI01 is cited by the very views that read them. |
| **D6** | The exit condition is **`trappoint migrate up` reaching 268/268 in one forward-only run**, not a continue-on-error census. | §0. The census number and the deployment number differ by 91 files today, and only one of them is a deployment. |
| **D7** | A new lint rule — *every schema-qualified relation a migration references has a producer in the same tree* — ships with this wave, and its **RED output is captured before the tables land**. | This wave fixes seven instances of one class of defect. Only the rule stops the eighth. A lint that has never been red asserts nothing (PL-2). |
| **D8** | **No conformance case implementation is edited.** W7 may fix the runner, the CLI, the packaging and the world builder; nobody touches a `cfNN_*.py`. | A worker who can edit cases is a worker who can make the census green by editing it. |
| **D9** | The conformance report publishes **PASS / FAIL / CANNOT-RUN per case**, with the reason for every cannot-run naming the missing object or role. | A suite that has never completed is worth demonstrating even at 30 % green; a suite whose reds were hidden is worth nothing. **A truthful red beats a fabricated green.** |
| **D10** | The gate proof is upgraded to assert the trigger did the projection, not merely to stop apologising for doing it by hand. | Removing a caveat is a subtraction. Reading back the outbox row the trigger emitted is an addition, and it is the strongest single sentence this repository can say. |
| **D11** | Each worker uses **its own database** on the shared local node (`prod_w<N>`), created and dropped by itself; nobody spawns a container. | Ten workers doing DDL in one database interleave; a database per worker is free on a single node. `packages/trappoint-testkit` already publishes the shared node under four DSN spellings. |
| **D12** | The eleven relations named only by `GRANTS.yaml` (`propagation`, `observed_assertion`, `merge_conflict`, `frontier_move`, `discordance_warrant`, `coverage_certificate`, `drift_finding`, `lesson`, `resolution_memory`, `time_witness`, `mainline_meas.assay_outcome`, `mainline_meas.external_attestation`) are **reported, not authored**. | None blocks a migration. Authoring eleven speculative tables is a second domain's work smuggled into a repair wave, and W9 will publish the six that cost a conformance case as cannot-run with the object named. |

---

## 3 · SEQUENCING

```
  wave A (fully parallel — disjoint files, disjoint databases)
        ┌── W1  allocation prose + producer-existence lint (captures the RED first)
        ├── W2  0049d identity_assignment + 0145f weld
        ├── W3  0089  agent_action + 0149a weld
        ├── W4  0089a person_measure_policy + 0089b standing + 0149b weld
        ├── W5  0090 patrol_run · 0099 outbox · 0099a site_register_signal
        └── W7  conformance runner wiring   (touches no migration; starts immediately)
                        │
        ┌───────────────┴───────────────┐
        ▼                               ▼
  wave B                          wave B'
  W6  268/268 through the         W8  THE GATE PROOF, caveat retired,
      real runner; lock;              trigger-projection asserted
      MIGRATIONS.md; grants          (needs W2-W5 only)
                        │
                        ▼
  wave C  W9  conformance executed to completion; per-case census   (needs W6 + W7)
                        │
                        ▼
  wave D  W10 docs/HONESTY.md re-based on W6/W8/W9's artefacts
```

W1–W5 and W7 start immediately. W6 needs W2–W5. W8 needs W2–W5. W9 needs W6 and W7. W10 needs
W6, W8 and W9 — it may not write a number before the artefact that produces it exists, because
`tests/release/test_honesty_is_checkable.py` follows every reference and fails on a dangling one.

---

## 4 · THE TEN WORKERS

| id | title | owns |
|---|---|---|
| W1 | allocation prose + the producer-existence lint rule | `migrations.allocation.toml`, `lint.py`, `producers.py`, its tests, `evidence/producers/` |
| W2 | `mainline.identity_assignment` + append-only weld | `0049d`, `0145f`, one contract test |
| W3 | `mainline_meas.agent_action` + append-only weld | `0089`, `0149a`, one contract test |
| W4 | `person_measure_policy` + `standing` + weld | `0089a`, `0089b`, `0149b`, one contract test |
| W5 | `patrol_run`, `outbox`, `site_register_signal` | `0090`, `0099`, `0099a`, one contract test |
| W6 | 268/268 through `trappoint migrate up`; lock; manifest; grants | `migrations.lock.json`, `MIGRATIONS.md`, `scripts/chain/`, `docs/release/chain-268.md` |
| W7 | conformance runner wiring + MAINLINE world builder + capability probe | `cli.py`, `runner.py`, `capability.py`, `pyproject.toml`, `cases/_world.py`, one test |
| W8 | the gate proof: caveat retired, trigger projection asserted | `scripts/proof/gate_refusal.py`, its README, its release doc, its release test |
| W9 | the conformance suite executed to completion; per-case census | `scripts/qa/run_conformance_census.py`, `qa/conformance-census.json`, `docs/release/conformance-census.md`, `justfile` |
| W10 | `docs/HONESTY.md` re-based, and its checker taught the new families | `docs/HONESTY.md`, `tests/release/test_honesty_is_checkable.py`, `docs/STATE-OF-THE-BUILD.md` |

File ownership is literal and disjoint. Anything a worker needs and does not own goes in
`cross_domain_notes`; nobody edits another worker's path, and nobody edits a `cfNN_*.py`.

---

## 5 · WHAT WOULD MAKE THIS WAVE A FAILURE

1. **A green chain that nobody drove through `trappoint migrate up`.** Raw-file application with
   continue-on-error is how 246/261 came to be quoted for a tree that stops at file 156. The
   record run is forward-only, from a fresh database, with an attestation row per file, or it did
   not happen.
2. **A table that does not satisfy its consumers.** `tests/integration/algorithms/cbm/` re-points
   itself at the real `identity_assignment` automatically; `0164`/`0165`/`0166`/`0171`/`0172`/`0163`
   select named columns. Applying is necessary. *Selecting from the view* is the test.
3. **A conformance census that reports 71 skips as a demonstration.** Scope item (c) is
   pass/fail/cannot-run *per case*, each cannot-run naming the object or role that is missing.
4. **Retiring the `open_blocking` caveat without replacing it with a stronger claim.** The
   deliverable is not the absence of an apology; it is the outbox row the trigger wrote, read back
   into the evidence file.
5. **`docs/HONESTY.md` getting shorter.** It gets *more accurate*. The 155/261 finding in §0 is
   worse news than the number it replaces, and it goes in.
