<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# Schema expectations asserted in Python vs what the 271 migrations create — divergence census

**Analyst:** `w5-schema-expectations` · **Date:** 2026-08-13 · **Mode:** READ-ONLY

## Ground truth this report is measured against

Everything below is measured against a database **I chained myself**, not against another
worker's scratch DB and not by reading migration files.

```
$ .venv/Scripts/python.exe scripts/chain/apply_chain.py --database d_w5_schema_expectations \
      --keep --attest final --evidence-dir <scratchpad>/chain-evidence
chain: 271 file(s) on disk in D:\CoackroachDBxAWS\mainline\verticals\mainline\db\migrations
chain: database d_w5_schema_expectations (fresh; a halted run leaves a DIRTY version behind)
    cluster: CockroachDB CCL v26.2.5 (x86_64-pc-linux-gnu, built 2026/07/28 18:56:00, go1.25.5)
    gc.ttlseconds = 4500 (Cloud value 4500)
    migrate bootstrap: exit 0 in 132.9s
    migrate up --attest final: exit 0 in 265.6s
CHAIN  files 271  applied 271  failed 0  dirty False
CHAIN  runner exit 0 · fingerprint 4477902ca8e7d108ef9050c4f860e384c019c63cad5941202999b66106511540
CHAIN  VERDICT COMPLETE · 271/271 through `trappoint migrate up`
```

Then seeded through the deployment's own applier
(`scripts/deploy/seed_demo.apply_seeds`, i.e. `demo_world.sql` then `demo_permit.sql`):
both `OK`. Dump: **109 tables · 1221 columns · 1453 table_constraints · 336
key_column_usage · 107 referential_constraints · 684 pg_constraint · 28 routines · 36 enum
labels**, over schemas `mainline` (72), `mainline_audit` (14), `mainline_meas` (12),
`mainline_ops` (5), `mainline_qa` (3), `trappoint` (3). `SHOW search_path` → `"$user",
public` — **no `mainline` on the path**, so every unqualified relation name would fail.

## Verdict

**312 SQL string literals** extracted by AST from the eight demo-api modules,
`scripts/proof/gate_refusal.py`, `verticals/mainline/db/queries/*.sql` and the fourteen
`scripts/deploy/*.py`. 178 `PREPARE`d clean against the chained schema; 90 are DDL/session
statements skipped by design; the 44 that errored are 38 extraction artefacts (docstrings
beginning "Call…", f-string fragments, `%(name)s` binds, deliberate negative probes) and
6 real signals, all analysed below. **Every INSERT's column list equals its VALUES arity
(33 INSERTs checked numerically) and every `execute(SQL, params)` call site's placeholder
count equals its parameter-tuple length (139 call sites checked).** `gate_run.py:130`'s
`_DISPOSITION_SQL` is 36 columns / 36 values / 17 placeholders / 17 parameters — the
off-by-one the brief asked about **is not there**. All twelve GET reads and `/v1/health`
execute successfully end-to-end against the chained+seeded database.

**Pairs enumerated: 21. DIVERGENT: 5. LATENT: 3. HELD: 13.**

The slice is **not** clean, and the one finding that matters is the third NO-GO defect
still living at its second call site: `transitions._sign_disposition` derives
`signer_credential_id = sha256("cred"+"signer")` while `demo_world.sql` enrols
`digest('mainline-demo/credential/demo.signer')`. The column is **NOT** projected away —
measured — the foreign key is real, and the endpoint answers **409 with
`"outcome": "refused"`, `"class": "gate"`** — a gate refusal the gate never made. The
anti-regression test written for this exact defect (`test_credentials.py:438`) walks
`gate_run.py` only, and all 60-odd `test_transitions.py` tests run against
`gate_refusal.seed_history`, which enrols the *same derived expression*. The suite cannot
see it.

## Inventory

| # | value | definition A (file:line) | definition B (file:line) | status | held by | severity |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | `disposition.signer_credential_id` bound by `POST /v1/checks/{id}/disposition` | `transitions.py:971` `_sha("cred","signer")` | `demo_world.sql:124` `digest('mainline-demo/credential/demo.signer','sha256')` | **DIVERGENT** | NOTHING (`test_credentials.py:438` walks `gate_run.py` only) | **HIGH** |
| 2 | `disposition.countersigner_credential_id` idem | `transitions.py:973` `_sha("cred","cosigner")` | `demo_world.sql:132` | **DIVERGENT** | NOTHING | **HIGH** |
| 3 | "every column except four is projected" (used to justify #1/#2 as harmless) | `transitions.py:1004-1012` staged_note; `gate_run.py:124-129` | measured: 17 of 36 projected, 19 load-bearing incl. both credential ids | **DIVERGENT** | NOTHING | **HIGH** |
| 4 | `mainline.permit` CHECK count in prose | `reads.py:260` "seven of the thirteen CHECKs" | measured 7 of **16** | DIVERGENT | NOTHING | LOW |
| 5 | composite FK column order | `scenario.py:295`, `gate_run.py:592-594`, `transitions.py:949-951` "(check_id, receipt_id)" | `0066_disposition.sql:160` `fk_exposure FOREIGN KEY (receipt_id, check_id)` | DIVERGENT | NOTHING | LOW |
| 6 | `disposition.site_id` "projected away, so Terraform need not publish it" | `infra/modules/demo-api/main.tf:180-187` | measured: **projected** (`0102:208 NEW.site_id := v_site_id`) | HELD | `fn_disposition_project` (0102) | — |
| 7 | `disposition.competency_sha256` / `competency_source_id` (w2's digest pair) | `gate_run.py:624`, `transitions.py:978` | measured: **projected** — the client value is INERT | HELD | `0102:47` `@projects` | — |
| 8 | `_FINGERPRINT_SQL` returns ten columns CockroachDB names `count` | `scenario.py:46-49` docstring | measured `['count'] × 10` | HELD | `positional()` + `zip(strict=True)` at `gate_run.py:292` | — |
| 9 | both merge-record statements return two columns named `encode` | `scenario.py:47-48`, `gate_run.py:145-147`, `transitions.py:543-544` | measured `['encode','encode',…]` and `['encode','merged_at','encode','gate_epoch']` | HELD | `positional()`; `test_row_factory_contract.py` (collects: 420 demo-api tests) | — |
| 10 | no *other* demo-api statement has duplicate output names | implicit | 47 SELECT constants executed; only the 2 above collide | HELD | measurement (this report) | — |
| 11 | every INSERT column list ≡ VALUES arity ≡ parameter count | 33 INSERTs / 139 call sites | measured, 0 mismatches | HELD | NOTHING mechanical, but currently exact | — |
| 12 | `mainline.lesson` / `propagation` / `merge_conflict` do not exist | `reads.py:1960-1963` `_PROPAGATION_PROBE` | measured `to_regclass → NULL` for all three | HELD | the probe runs **on every request** and 501s if they appear | — |
| 13 | `trappoint.deploy_chain` is not created by the chain | `health.py:161-170` reads it | created only by `scripts/deploy/cloud_chain.py:194` | HELD | `health.py:261-267` fallback; measured `/v1/health → 200` | — |
| 14 | `crdb_internal.cluster_id()` / `gossip_nodes` readable | `capture_demo_bundle.py:729,733` | measured `42501 Access to crdb_internal … is restricted` | HELD | `capture_demo_bundle.py:742-744` records `(refused: 42501 …)` | LOW |
| 15 | gate objects exist under the names the proof probes | `gate_refusal.py:166-175` `GATE_OBJECTS` | all 8 resolve; `merge_permit` is `prokind='p'` and *is* in `information_schema.routines` | HELD | the probe itself | — |
| 16 | `mainline.merge_permit` arity 8 | `gate_run.py:120`, `transitions.py:497` | `merge_permit(uuid,bytea,text,text,jsonb,bytea,int2,bytea)` | HELD | the call | — |
| 17 | `trappoint.explain_refusal` arity 4 | `refusal.py:141` | `explain_refusal(text,uuid,text,jsonb) → jsonb` | HELD | `test_refusal_row_factory.py` | — |
| 18 | `blocking_check.dedupe_key` is a STORED generated column | `reads.py:598` `# pragma: no cover` | `is_generated=ALWAYS`, but `is_nullable=YES` | LATENT | NOTHING; unreachable in practice (`digest()` of NOT NULL inputs) | LOW |
| 19 | `permit.site_id` → `mainline.site` referential integrity | `scenario.py:288-289` INNER `JOIN mainline.site` | **no FK on `site_id` anywhere in the tree** (47 tables carry the column, 0 FK it) | LATENT | NOTHING | LOW |
| 20 | `db/queries/closure_read.sql`, `closure_write.sql` | both files | both `PREPARE` clean | HELD | `EXPLAIN-ASSERTIONS.md` CI | — |
| 21 | every schema-qualified name in 178 statements | demo-api + proof + deploy | all resolve; **zero unqualified `mainline` names**, so `search_path` cannot matter | HELD | qualification is exhaustive | — |

---

## Findings

### F-05-1 `transitions._sign_disposition` still derives the credential id the FK rejects — severity: HIGH

- **Divergence:** `verticals/mainline/apps/demo-api/src/mainline_demo_api/transitions.py:971`
  binds `_sha("cred", "signer")` = `487adc50409e8811b1f12055ee183ce9d8548f11262807d01776fb67cd09c765`
  into `signer_credential_id` (and `:973` `_sha("cred","cosigner")` into
  `countersigner_credential_id`) ·
  `verticals/mainline/db/seeds/demo/demo_world.sql:124` enrols
  `digest('mainline-demo/credential/demo.signer','sha256')` =
  `ff356d1461921438bbbc5d644db8793669cb948a46bddc2e8fb5ebef959bdf0c` ·
  `verticals/mainline/db/migrations/0066_disposition.sql:117-118`
  `signer_credential_id BYTES NOT NULL REFERENCES mainline.signing_credential (credential_id)`.

  This is the beat-4 defect verbatim. `gate_run.py:456-457` was fixed to
  `resolve_credential_id`; **`transitions.py` was not**, and it is the module behind
  `POST /v1/checks/{check_id}/disposition`, one of the four kernel transitions declared in
  `contracts/invoke.schema.json`.

- **Command:**
  ```
  .venv/Scripts/python.exe <scratchpad>/probe_disposition.py     # section B
  ```
- **Output:**
  ```
  placeholders in _SIGN_SQL: 19  params passed: 19
  column list length: 36
  signer_credential_id the code derives: 487adc50409e8811b1f12055ee183ce9d8548f11262807d01776fb67cd09c765
  signer_credential_id the seed enrolled: ff356d1461921438bbbc5d644db8793669cb948a46bddc2e8fb5ebef959bdf0c
  RESULT: REFUSED [23503] insert on table "disposition" violates foreign key constraint
  "disposition_signer_credential_id_fkey" DETAIL: Key (signer_credential_id)=
  ('\x487adc50409e8811b1f12055ee183ce9d8548f11262807d01776fb67cd09c765') is not present in
  table "signing_credential".
  ```

- **What a user or judge sees:** the endpoint answers **HTTP 409 with a complete gate-refusal
  envelope** — `outcome: "refused"`, `refusal.class: "gate"`,
  `refusal.constraint: "disposition_signer_credential_id_fkey"`,
  `constraint_source: "reported"`, provenance chips `db:constraint`. Measured through the
  real entry point:

  ```
  .venv/Scripts/python.exe <scratchpad>/probe_endpoint.py
  HTTP status: 409
   "data": {"procedure": "trappoint.sign_disposition", "outcome": "refused",
            "refusal": {"class": "gate", "constraint": "disposition_signer_credential_id_fkey",
                        "sqlstate": "23503", "constraint_source": "reported"}}
  dispositions on the check afterwards: (0,)
  ```

  The console's `transport.ts` turns that into a `RefusalError` and renders it as the gate
  deciding. Nothing about the gate was exercised: a row is simply missing. This is exactly
  the failure `gate_run.py:36-39` says it removed — *"an exhibit the gate never produced"* —
  reproduced one module over. For contrast, the other three transitions are honest on the
  same database:

  ```
  merge_permit         409  outcome=refused  sqlstate=23514  constraint=gate_closed_when_issued   source=reported
  suspend_permit       409  outcome=refused  sqlstate=23503  constraint=legal_edge                source=reported
  materialise_checks   200  outcome=committed
  sign_disposition     409  outcome=refused  sqlstate=23503  constraint=disposition_signer_credential_id_fkey
  ```

- **What would have caught it: NOTHING DOES.** Two mechanisms exist and both miss it by
  construction:
  1. `verticals/mainline/apps/demo-api/tests/test_credentials.py:438`
     `test_gate_run_derives_no_credential_id` parses **`GATE_RUN_SOURCE`** only
     (`test_credentials.py:96`); its own docstring at `:451-453` says "The other `_sha` call
     sites in that file are left alone". Widening it to `transitions.py` is a one-line fix
     and would have failed today.
  2. Every test in `test_transitions.py` takes `w4_conn`, and `w4_database`
     (`test_gate_run.py:414`, re-exported at `test_transitions.py:38`) builds its world with
     `scripts/proof/gate_refusal.py::seed_history`, which at `gate_refusal.py:844` sets
     `signer_cred, cosign_cred = _sha("cred","signer"), _sha("cred","cosigner")` and enrols
     exactly those bytes at `gate_refusal.py:876-883`. **The fixture and the code share the
     expression**, so `test_sign_disposition_then_merge_commits`
     (`test_transitions.py:562`) passes:
     ```
     $ .venv/Scripts/python.exe -m pytest \
         "verticals/mainline/apps/demo-api/tests/test_transitions.py::test_sign_disposition_then_merge_commits" -x -q
     1 passed in 1.21s
     ```
     No test in `test_transitions.py` uses the `demo_world.sql` fixture — measured:
     ```
     test_transitions.py:      w4_conn
     test_credentials.py:      conn: psycopg demo_world_conn
     test_refusal_row_factory.py: conn: psycopg demo_dsn
     ```

- **Fix (for the next wave, not applied here):** replace `transitions.py:971,973` with
  `resolve_credential_id(conn, signer_sub)` / `(conn, countersigner_sub)` — resolved before
  the write, so an unenrolled subject is `422 demo_history_not_seeded` and not a fabricated
  refusal — and change `test_credentials.py:438` to walk both source files.

### F-05-2 The sentence that makes F-05-1 look harmless is false — severity: HIGH

- **Divergence:** `transitions.py:1004-1012` tells the reader, in the response body a judge
  reads, that "**the credential identifiers are generated, not produced by a security key**
  … Every other column on the row … **is projected by fn_disposition_project from
  authoritative rows and is real**". `gate_run.py:124-129` makes the same claim: "Every
  column on this row except the four a signer actually chooses is PROJECTED … and the values
  supplied here are overwritten (invariant I02)." · Measured against
  `verticals/mainline/db/migrations/0102_fn_disposition_project.sql:47` (`@projects`) and the
  live trigger: **17 of 36 columns are projected; 19 are load-bearing, and both credential
  ids are among the 19.**

- **Command:** `.venv/Scripts/python.exe <scratchpad>/probe_projection.py` — binds a
  distinguishable sentinel into all 36 columns and diffs submitted vs stored, in a
  transaction that is rolled back. (Re-run with inverted booleans after the first pass
  showed a confound: for `(blood_major, applied)` the lattice's `req_*` are all `false`, so
  submitting `false` could not distinguish "kept" from "projected to the same value".)

- **Output (final, disambiguated):**
  ```
  PROJECTED AWAY (17):
     site_id, virulence, closure_gen, signer_rank, signer_org, competency_snapshot,
     competency_source_id, competency_sha256, req_compensating, req_second_signer,
     req_foreign_org, req_predicate, req_reassert, min_signer_rank, severity_snapshot,
     deliberation_seconds, prior_override_count
        site_id              00000000-…-0000000000ff -> dec0de00-0001-4000-8000-000000000001
        virulence            routine                 -> blood_major
        signer_rank          1                       -> 5
        min_signer_rank      9                       -> 3
        deliberation_seconds 4242                    -> 969704
        req_second_signer    True                    -> False
  LOAD-BEARING (19): disposition_id, check_id, receipt_id, subject_kind, permit_id, kind,
     defeater_code, defeater_vocab_sha256, rationale, evidence_sha256, signer_sub,
     signer_credential_id, countersigner_sub, countersigner_credential_id, signature_alg,
     authenticator_data, client_data_json, user_verified, evidence_opened
  ```

- **What a user or judge sees:** nothing directly — this is a claim, not a code path. Its
  consequence is F-05-1: a reviewer who believed the staged note would conclude that a
  synthesised credential id cannot matter, and stop reading. It is ranked HIGH because it is
  the *reason* three review rounds walked past `transitions.py:971`, and because the
  sentence is published to a judge inside `envelope.staged_note`.

- **Value for the lead's §2.6 open question** ("which client-supplied disposition columns are
  projected away and which are load-bearing is the single highest-value question in this
  census"), now answered by measurement rather than reading:
  - **INERT** (w2 may deprioritise): `competency_sha256`, `competency_source_id`,
    `competency_snapshot`, `site_id` — all overwritten. `infra/modules/demo-api/main.tf:180-187`'s
    argument for omitting `MAINLINE_DEMO_SITE_ID` **is correct**, and now proven:
    submitted `00000000-…ff`, stored `dec0de00-0001-…`.
  - **LOAD-BEARING** (w2 must treat as real): `signer_credential_id`,
    `countersigner_credential_id`, `defeater_vocab_sha256`, `evidence_sha256`,
    `authenticator_data`, `client_data_json`. Only the first two are FK-enforced; the other
    four carry `length(...) = 32` CHECKs and no FK, so a wrong digest there is stored, not
    refused.

- **What would have caught it: NOTHING DOES.** No test compares a submitted disposition row
  with the stored one.

### F-05-3 `reads.py` states a CHECK count the migrations no longer match — severity: LOW

- **Divergence:** `verticals/mainline/apps/demo-api/src/mainline_demo_api/reads.py:260`
  "On `mainline.permit` that selects exactly seven of the **thirteen** CHECKs" ·
  the chained schema has **16** CHECKs on `mainline.permit`.
- **Command / Output:**
  ```
  permit gate constraints: 7 ['merge_evidence', 'reading_floor_when_issued',
    'no_open_warrant_when_issued', 'identity_conserved_when_issued',
    'boundary_certified_when_issued', 'gate_closed_when_issued', 'conflicts_resolved_when_issued']
  total CHECKs on mainline.permit: 16
  change_request gate constraints: 4
  ```
- **What a user or judge sees:** nothing. The *selection* (7, and 4 for `change_request`) is
  correct and catalogue-driven, exactly as the docstring promises; only the denominator is
  stale. Reported so the next wave does not spend an hour re-deriving it.
- **What would have caught it:** NOTHING DOES — it is prose. A one-line assertion in
  `test_reads.py` on `len(_gate_constraints(...)) == 7` would pin the number that matters.

### F-05-4 The composite foreign key is written down in the wrong column order — severity: LOW

- **Divergence:** `scenario.py:295-296`, `gate_run.py:592-594`, `transitions.py:949-951` and
  `reads.py`'s docstrings all say "a disposition's composite foreign key lands on
  **(check_id, receipt_id)**" · `verticals/mainline/db/migrations/0066_disposition.sql:160`
  declares `CONSTRAINT fk_exposure FOREIGN KEY (receipt_id, check_id) REFERENCES
  mainline.exposure_line (receipt_id, check_id)`.
- **Command / Output:**
  ```
  [f] fk_exposure: FOREIGN KEY (receipt_id, check_id) REFERENCES mainline.exposure_line(receipt_id, check_id)
  [p] pk_exposure_line: PRIMARY KEY (receipt_id ASC, check_id ASC)
  ```
- **What a user or judge sees:** nothing — FK semantics are pairwise and the *meaning* the
  prose asserts ("a signature may only cite a receipt that actually showed this obligation")
  is exactly right. Cosmetic; listed only so the census is complete and nobody re-audits it.
- **What would have caught it:** NOTHING DOES.

### F-05-5 `mainline.permit.site_id` is joined as if it were a foreign key, and it is not — severity: LATENT / LOW

- **Divergence:** `scenario.py:288-289` `_RESOLVE_SQL` uses an **INNER** `JOIN mainline.site
  st ON st.site_id = p.site_id`, and a missing site row therefore makes `resolve()` raise
  `ScenarioNotSeeded("no mainline.permit with permit_id …")` — a message about the wrong
  row · **no table in the tree foreign-keys `site_id` to `mainline.site`**.
- **Command / Output:**
  ```
  which mainline tables carry site_id, and which of them FK it to mainline.site?
      mainline.permit                     site_id FK -> mainline.site : NO
      mainline.disposition                site_id FK -> mainline.site : NO
      … 47 relations carry the column; none of them FK it.
  ```
  The condition is hard to reach in the seeded world — the site row is pinned indirectly:
  ```
  DELETE refused [23503] delete on table "site" violates foreign key constraint "fk_site"
  on table "ledger_intake"
  ```
  so this is recorded honestly as LATENT rather than as a live defect. `reads.py:308` uses
  `LEFT JOIN` for the same relationship, which is the safer of the two spellings; the two
  modules disagree about a relationship neither schema nor test constrains.
- **What would have caught it:** NOTHING DOES.

---

## Pairs checked and found to agree, with the mechanism that holds them

- **Arity, everywhere.** 33 INSERTs: every column list equals its VALUES list.
  `gate_run._DISPOSITION_SQL` = 36/36/17 placeholders/17 params;
  `transitions._SIGN_SQL` = 36/36/19/19; `gate_refusal.py:1419` and
  `capture_demo_bundle.py:404` = 36/36/17/17. 139 `execute()` call sites: placeholder count
  equals parameter-tuple length at all of them. (One static false positive,
  `gate_refusal.py:495`, is `(*owner.split("."), name)` where every `GATE_OBJECTS` trigger
  entry is `"schema.table"` — three values, correct.) *Held by:* nothing mechanical. This is
  the pair most worth a guard: a `%s`-count-vs-`len(params)` lint over these files is cheap
  and would fail loudly.
- **Duplicate output names.** 47 SELECT constants executed and their `cursor.description`
  read. Exactly two collide, both in `gate_run` and both already read through
  `scenario.positional()`: `_FINGERPRINT_SQL` → ten columns named `count`,
  `_MERGE_RECORD_SQL` → `['encode','encode','gate_epoch','merged_at','state','open_blocking','head_seq']`.
  The inline statement at `transitions.py:547-548` → `['encode','merged_at','encode','gate_epoch']`.
  **All 35 `reads.py` constants are collision-free**, so `reads`'s `dict_row` convention is
  safe. `scenario.py:46-49`'s claim is accurate in every particular. *Held by:*
  `positional()`, `zip(..., strict=True)` at `gate_run.py:292`, and
  `test_row_factory_contract.py` — which now collects (420 demo-api tests collected).
- **All twelve reads and `/v1/health` run.** Driven through `db.connection()` (i.e. with
  `row_factory=dict_row`, as production opens it) against the chained+seeded database: all
  twelve return payloads; `/v1/health` → `200`,
  `schema_fingerprint 4477902ca8e7d108ef9050c4f860e384c019c63cad5941202999b66106511540`,
  `migrations_applied 271`, `applied_by "trappoint migrate up"`. *Held by:* the reads
  themselves plus `test_reads.py`.
- **`trappoint.deploy_chain` absent after the chain.** `health.py:161-170` selects it;
  the 271 migrations never create it (`scripts/deploy/cloud_chain.py:194` is the only
  `CREATE TABLE`). *Held by:* `health.py:261-267`'s `UndefinedTable` fallback to
  `HEALTH_STATEMENT_WITHOUT_DEPLOY_CHAIN` and `row.get(...)` at `:307-308` — measured
  working, `200`, `deploy_chain_applied: None`. `demo_acceptance.py:589-602` raises an
  advisory rather than failing. This is a correctly-handled two-appliers/two-ledgers split.
- **`mainline.lesson` / `propagation` / `merge_conflict` really do not exist**, and
  `read_propagation` is the best-held pair in this slice: `reads.py:1960-1963` runs
  `to_regclass` on all three **on every request** and raises `501` if any appears
  (`reads.py:2011-2018`), so the staged payload cannot outlive the absence it declares.
- **`crdb_internal` is restricted on v26.2.5** (`42501 Access to crdb_internal and system is
  restricted`) for `cluster_id()`, `gossip_nodes`, `jobs`, `tables`.
  `capture_demo_bundle.py:742-744` catches it and records `(refused: 42501 …)`; the region
  then falls back to host inference at `:760-767`. Held, but flagged for **W7/W9**: a
  captured bundle's `cluster_id` will read as a refusal string, not an id.
- **Gate objects, procedure arities, enum casts.** All eight `GATE_OBJECTS` resolve
  (`merge_permit` is `prokind='p'` and *is* listed in `information_schema.routines` on this
  version, so `gate_refusal.inspect_gate_objects` is sound);
  `mainline.merge_permit(uuid,bytea,text,text,jsonb,bytea,int2,bytea)` matches the 8-arg
  `CALL`; `trappoint.explain_refusal(text,uuid,text,jsonb)→jsonb` matches `refusal.py:141`;
  `reads._LATTICE_SQL`'s `%s::mainline.virulence_class` resolves.
- **Schema qualification.** All 178 preparable statements name their schema. `SHOW
  search_path` is `"$user", public` on my connection and would be the demo role's name in
  the Lambda — irrelevant, because nothing is unqualified. The `mainline_audit` view names
  interpolated at `reads.py:2196` come from `information_schema.views` filtered to that
  schema and are re-checked with `str.isidentifier()`.
- **`db/queries/closure_read.sql` and `closure_write.sql`** both `PREPARE` clean against the
  chained schema.
- **`transitions._RECEIPT_SQL` / `_APPEND_EVENT_SQL` / `_MERGE_SQL`** — every named column
  exists; the only NOT-NULL-without-default columns absent from any demo-api INSERT list are
  the ten on `mainline.refusal_ledger`, and the two INSERTs that name it
  (`cloud_roles.py:665`, `judge_access.py:281`) are deliberate one-column *denial* probes
  expecting `42501`.

## Not reached (and why)

- **Whether the deployed Cloud `mainline_demo` schema equals this chain.** I have no Cloud
  credentials and made no network call. Everything here is the local chain plus the seed
  files the deploy script applies; `health.py`'s `schema_fingerprint` is the value that would
  settle it, and `demo_acceptance.py` already compares it. → **W9 / w1-demo-identity.**
- **Whether the projected `req_*` / `min_signer_rank` values are *enforced* correctly.** I
  measured that `fn_disposition_project` overwrites them from `mainline.clearance_legal`
  (submitting `req_compensating=true` for `kind='mitigated'` produced
  `23514 needs_compensating` — the projection wrote `true` and the CHECK then bit). Whether
  that constitutes MI-catalogue conformance is **W6's**, not mine.
- **JSON response shapes** for any of the payloads above → **W8**.
- **`test_row_factory_contract.py`'s pass/fail state and the collection question generally**
  → **W4**. I confirmed only that 420 demo-api tests now collect.
- **`mainline_mcp.client` and `mainline_meas.external_attestation`** in
  `judge_access.py:99,1503` are a Python module path and quoted prose respectively, not SQL
  relations. Not divergences.
- **Note on my scratch database.** `d_w5_schema_expectations` was left in a mutated state
  *after* all measurements were taken: the final probe drove
  `materialise_checks` with `MAINLINE_DEMO_ALLOW_MUTATION=1`, which committed and moved the
  demo permit `dispositioned → checks_materialised`, `head_seq 2 → 3`. Every measurement in
  this report was taken before that, and every disposition INSERT was rolled back.
  `d_w5` is a second, earlier chain of mine and should be treated as contaminated (a
  concurrent fast-apply re-ran 60 files into it); use `d_w5_schema_expectations` or rebuild.
