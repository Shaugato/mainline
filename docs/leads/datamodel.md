<!--
SPDX-FileCopyrightText: 2026 MAINLINE
SPDX-License-Identifier: CC-BY-4.0
-->

# DATA MODEL LEAD — domain implementation plan

**Domain:** the memory itself. The full MAINLINE schema (ARCHITECTURE §5), the migration order (§18),
the role/grant matrix (§11.2), RLS (§11.3), the TTL policy (§4.1 law 13), the migration runner
contract, and the `MI01–MI30` invariant catalogue (§16).

**Authority:** `ARCHITECTURE.md` wins on design; `BUILD_PLAN.md` wins on order and evidence.
This document decides only what those two leave open, and every such decision is numbered `DM-n`
with its justification on the same line.

---

## 0. The one thing this domain must get right

Everything ancestry-conditioned in MAINLINE reads **one scalar** — `clause_blame_current.max_severity`
and the `virulence` banded from it. Every gate, every clearance-lattice `23503`, every drift finding,
every `weaken_over_blood` check is a function of that scalar. The adversarial review's two
build-blocking findings (S1, S2) were both *"a projection was trusted rather than enforced"*.

So the domain's success criterion is not "79 tables exist". It is:

> **Every column a `CHECK` or a composite FK reads is written by a trigger from a named authoritative
> table, the trigger `RAISE`s when that table has no row, and there is a machine-checkable list of
> every such column that CI walks on every PR.**

That list is `TRIGGER-MAP.yaml` (worker `dm-functions-triggers`), and the test that walks it is the
single most valuable artefact this domain produces after the DDL itself. It is the generalisation of
`CF-07` and `CF-19` from two hand-written cases into a property over the whole schema.

---

## 1. Strategy

### 1.1 Sequencing — dependency order, not §18 order

§18's numbers are a **range map for ordering**, not a file map. The build proceeds in seven strata,
each of which is testable before the next exists:

```
S0  runner + registry + invariant catalogue + the red harness          (nothing depends on a cluster)
S1  schemas · roles · types · lattice seeds · site · person            0001–0023
S2  commit DAG · doc · clause · clause_version · embeddings sidecar    0024–0031, 0047–0049
S3  activity · event · blame_edge · clause_blame_closure · the view    0032–0039
S4  cue entity + two vector sidecars + BM25 tables + bonds             0040–0046
S5  permit · change_request · blocking_check · receipts · predicates   0050–0065
S6  disposition family · merge_record (the epoch pin)                  0066–0071   ← G0-gated
S7  ledger · measurement · fixity · fleet · governance · ops           0072–0129
S8  FUNCTIONS then TRIGGERS — the enforcement layer                    0130–0199
S9  audit views · qa views · RLS policies · the deferred cycle FK      0200–0279
```

The critical property of this order: **S1–S7 are inert tables.** Nothing refuses anything until S8.
That is deliberate — it means the entire schema can be reviewed as data shapes before any behaviour
exists, and it means S8 lands against a schema that is already frozen, so a trigger author never has
to negotiate a column definition. The cost is that most `MI*` tests are red from S1 to S8, which is
exactly what PL-2 wants and is turned into a mechanical control by DM-8 below.

### 1.2 Red before green, made mechanical (PL-2)

A suite that has never been red asserts nothing, and a solo founder with coding agents accumulates
confidently-written tests that assert nothing faster than anyone else. So red-before-green is not a
habit here, it is a CI gate driven by data:

`verticals/mainline/db/invariants/mi_catalogue.yaml` carries, per invariant:

```yaml
- id: MI25
  statement: blocking_check.severity and .virulence are projections of the blame closure, never inputs
  instantiates: I02
  mechanism: fn_check_project, raising on a missing closure
  sqlstate: P0001
  owning_migrations: [0058, 0130]
  owning_tests: ["tests/integration/schema/test_mi_projection.py::test_mi25_check_projection"]
  status: pending          # pending | enforced
```

The `db-schema.yml` workflow runs two jobs against the same suite:

* **`mi-green`** — every `enforced` invariant's owning tests must pass.
* **`mi-red`** — every `pending` invariant must have **at least one owning test that currently fails**.
  A `pending` invariant whose tests all pass fails CI with
  `MI25 is pending but its tests pass — promote it in mi_catalogue.yaml`.

Promotion from `pending` to `enforced` is therefore a PR that shows up in blame, and the ratchet is
one-way (CI fails a demotion without an `ADR-` reference in the commit body). This is the product's
own O-Ring Ratchet applied to its own test suite, it costs about 120 lines, and it makes "we wrote
the failing test first" checkable by a stranger rather than asserted by us.

### 1.3 Interfaces this domain publishes

| Artefact | Consumer | Contract |
|---|---|---|
| `verticals/mainline/db/migrations/*.up.sql` | provisioning agent, CI, restore drill | forward-only, one statement per file, header-linted |
| `verticals/mainline/db/migrations.lock.json` | runner, CI coverage check, honesty card | file ⇄ number ⇄ MI ids ⇄ sha256 ⇄ counsel_gated |
| `verticals/mainline/db/invariants/mi_catalogue.yaml` | CI ratchet, `MECHANISMS.md`, submission | MI ⇄ mechanism ⇄ SQLSTATE ⇄ migrations ⇄ tests ⇄ status |
| `verticals/mainline/db/GRANTS.yaml` | provisioning, privilege-probe test | role ⇄ object ⇄ privilege, declarative, re-asserted |
| `verticals/mainline/db/RLS-MATRIX.yaml` | policy migrations, RLS test | table ⇄ policy ⇄ role ⇄ command ⇄ permissive/restrictive |
| `verticals/mainline/db/TRIGGER-MAP.yaml` | the P2 property test | projected column ⇄ function ⇄ authoritative table ⇄ raise SQLSTATE |
| `verticals/mainline/db/TTL-ALLOWLIST.yaml` | TTL negative test | exactly three tables, none in schema `mainline` |
| `verticals/mainline/db/GSAC.md` | gate lead, disposition lead, console | how a row addresses a gated subject |
| `verticals/mainline/db/queries/*.sql` | projector service, recall agent | committed statements with `EXPLAIN` assertions |
| `packages/trappoint-migrate` | K1, K6, restore drill | `apply · verify · fingerprint · attest · lint · grants apply` |
| `trappoint_migrate.attest.LedgerSink` (Protocol) | custody lead | `emit(kind, subject_id, payload) -> None`; default is a no-op recorder |

Everything else in the repository consumes those seven files. No other domain edits them.

---

## 2. Decisions

These are the places the two authoritative documents leave a genuine choice, or contain a shape that
does not compile. Each is one line of justification.

**DM-1 · `merge_record` carries two nullable subject columns and two MATCH SIMPLE composite FKs.**
§5.5 says the two epoch pins are "a partial-FK pair, one per kind"; SQL has no conditional FK.
CockroachDB's default `MATCH SIMPLE` treats a composite FK as satisfied when *any* column is NULL, so
`(permit_id, gate_epoch) → permit(permit_id, gate_epoch)` and `(cr_id, gate_epoch) → change_request(cr_id, gate_epoch)`
coexist on one row, both `ON UPDATE RESTRICT ON DELETE RESTRICT`, with `exactly_one_subject` making
the disjunction total. — *because the alternative (two tables) breaks `PRIMARY KEY (subject_kind, subject_id)`
and therefore breaks "at most one merge per subject, ever".*

**DM-2 · GSAC — the Gated Subject Addressing Convention — is applied uniformly.**
`subject_kind STRING` + `permit_id UUID NULL` + `cr_id UUID NULL` + `subject_id UUID NOT NULL AS
(coalesce(permit_id, cr_id)) STORED` + `exactly_one_subject` + `subject_matches`, on `blocking_check`,
`exposure_receipt`, `disposition`, `override_ledger` and `merge_record`. — *because S16 made
`change_request` a gated subject, and without this `MI30` is unsatisfiable: a CR-scoped check could
never be dispositioned, since `fn_disposition_project` reads `blocking_check.permit_id` and would
`RAISE` on every CR check.*

**DM-3 · `mainline.site` ships, and `site_role`, `site_code` and `tenant_id` are projected from it.**
§5 has `site_id` on 40 tables, `permit.site_role NAME` filled by `fn_site_role`, `ledger_intake.site_code`
and `event_cue_coarse.tenant_id` — with no authoritative table behind any of them. — *because P2
forbids a gate-adjacent column with no authoritative source, and `site_role` is the RLS scope token.*

**DM-4 · No `CHECK` expression contains a JSONB operator, a subquery, `now()`, or any function whose
immutability is not documented.** `waiver_authority` becomes
`CHECK (virulence NOT IN ('blood_major','blood_fatal') OR has_isolation_authority)` over a
trigger-projected `has_isolation_authority BOOL NOT NULL` derived from the frozen `competency_snapshot`.
— *strictly stronger under P2 (the flag is written by the same trigger that freezes the snapshot) and
it removes `GT-13`'s JSONB-`?`-in-CHECK dependency from the critical path.*

**DM-5 · Tests assert behaviour, never mechanism, for computed columns.** `blocking_check.dedupe_key`
and `permit_event.chain_digest` ship as `STORED` computed columns exactly as §5 specifies; the `MI`
tests assert *dedupe absorbs a duplicate* and *a forged `prev_digest` is refused*. — *so that if
`GT-13` fails, swapping to a `BEFORE INSERT` trigger assignment is a one-file change with zero test churn.*

**DM-6 · Secondary indexes are declared inline in `CREATE TABLE`, including partial and inverted ones.**
— *one statement per file survives without an index-file explosion, and every index exists from row
zero, which also satisfies the vector-index rule (declare inline, create the table empty) for free.*

**DM-7 · Roles and grants leave the migration set and become a declarative, idempotently re-asserted,
attested matrix** (`GRANTS.yaml`, applied by `trappoint-migrate grants apply`). Migrations `0006–0009`
keep only the four statements that are genuinely schema: create `mainline_owner` (NOLOGIN), transfer
schema ownership, `REVOKE ALL … FROM public`, and a marker file citing the matrix. — *because role
membership and grants are cluster state that a `RESTORE` into a new cluster does not carry, so they
must be re-asserted and drift-checked, not applied once; and because the real control is the
privilege-probe test that asserts `42501` per role per object, not the DDL that granted them.*

**DM-8 · The invariant catalogue is machine-readable and CI-ratcheted** (§1.2 above). — *because
"every migration cites at least one invariant ID" (§18) is only enforceable against a registry, and
because PL-2 needs a mechanism, not a memory.*

**DM-9 · `mainline.clause_blame_current` is the only read path to the closure.** A CI grep fails any
migration, query or view referencing `clause_blame_closure` outside `0038`, `0039` and
`queries/closure_write.sql`. — *`max(closure_gen)` discipline must be structural; one forgotten call
site silently reads a superseded generation.*

**DM-10 · Every constraint, index and policy is explicitly named; a test fails on any
system-generated name in the `mainline*` schemas.** — *the constraint name is the courtroom exhibit;
`check_permit_1` is not an exhibit.*

**DM-11 · Lookup vocabularies are FK'd tables, not free-text `CHECK IN (...)`, wherever a *writer
outside the schema* supplies the value.** Specifically `mainline_ops.outbox_kind` and
`mainline.ledger_entry_kind`. — *a changefeed router keyed on a free-text column drops a typo
silently; an FK makes it `23503`.*

**DM-12 · All seed data is timestamp- and identity-deterministic** — fixed literal `TIMESTAMPTZ`s and
`uuid5(MAINLINE_NS, natural_key)`, never `now()` or `gen_random_uuid()`. — *the schema+seed
fingerprint is the dev/demo/prod parity gate; a `now()` in a seed makes parity unprovable.*

**DM-13 · The migration runner owns its own bookkeeping schema (`trappoint_migration`), created
idempotently on connect, outside the numbered set.** — *otherwise migration `0001` cannot record that
it ran.* Lock table is a real table with a CAS acquire (CockroachDB has no advisory locks);
`force` requires `--incident <id>` and writes a ledger entry; a `dirty` marker names the failing file
and refuses to advance.

**DM-14 · `.down.sql` is illegal at or below the protected floor (everything ≤ the last trigger file).**
Views and policies above the floor may carry one. — *down-migrating an append-only ledger is not a
rollback, it is destruction of evidence, and `mainline-schema down` must fail before it reaches the
cluster, not after.*

**DM-15 · `recall_run` stays permit-scoped; `disposition`, `exposure_receipt` and `override_ledger`
do not.** — *CR-scoped checks are produced deterministically by `fn_weaken_materialise` (channel A),
which needs no retrieval, so generalising `recall_run` would add a nullable column that is always NULL.*

**DM-16 · Missing objects that the role matrix, RLS or §11 reference but §5 never defines are added
minimally rather than left dangling:** `mainline.document_intake_finding`, `mainline_meas.assay_outcome`,
`mainline.disposition.peer_visible BOOL NOT NULL DEFAULT false` (the `peer_blind` policy reads it),
`mainline.disposition.dictated_by_sub STRING NULL` with `dictation_needs_second_credential`.
— *a `GRANT` on a non-existent table is a migration that fails on a fresh cluster and nowhere else.*

**DM-17 · Counsel-gated files ship with their DDL and a conservative *policy*, not with variant DDL.**
`0066–0069` and `0086` carry a mandatory header block
(`-- COUNSEL-GATED: yes (G0) · DEFAULT: conservative · ADR: docs/adr/0001-g0-counsel.md`) and the
switchable surface lives in `verticals/mainline/db/ext/disposition_ext/`: the `clearance_legal` seed
variant (conservative = the three absent cells stay absent, so no `mechanism_absent` and no
`accept_residual` over fatal ancestry), `evidence_opened` recorded, `silence_ledger` in the
unprivileged `mainline_meas` zone. — *because the shape must be **configuration**, per BUILD_PLAN §2.1;
a DDL fork per legal answer is two schemas to test and one to get wrong.*

---

## 3. Banding — how ten workers touch one numbered sequence without colliding

Each worker owns a contiguous, disjoint band. Within a band a worker allocates freely. The anchors
cited by BUILD_PLAN §2.1 are preserved exactly: **`0001–0065` are counsel-independent**;
**`0066` disposition · `0067` disposition_citation · `0068` override_ledger · `0069` carried_disposition ·
`0086` silence_ledger** are the counsel-gated five.

| Band | Worker | Contents |
|---|---|---|
| — | `dm-runner` | runner, registry, MI catalogue, red harness, `db-schema.yml` |
| 0001–0023 | `dm-foundation` | schemas, owner/ownership/revoke, 7 types, `subject_transition`, `clearance_legal`, `retention_class`, `adm_decision_class`, `site`, `person`, `signing_credential` |
| 0024–0031, 0047–0049 | `dm-spine` | `commit_obj`, `commit_edge`, `ref`, `doc`, `clause`, `clause_version`, `clause_band`, `clause_embedding`; `control_series`, `carriage`, `identity_residue` |
| 0032–0039 | `dm-blame` | `activity_node`, `event`, `event_edge`, `control_failure`, `event_severity_revision`, `blame_edge`, `clause_blame_closure`, `clause_blame_current` |
| 0040–0046 | `dm-recall-tables` | `event_cue`, `event_cue_embedding`, `event_cue_coarse`, `lex_posting`, `lex_stats`, `lex_doclen`, `event_bond` |
| 0050–0065 | `dm-gate` | `permit`, `change_request`, scope tables, `boundary_certificate`, `blocking_check`, `permit_event`, `cr_event`, receipts, `defeater_option`, `mechanism_predicate` |
| 0066–0071 | `dm-disposition` | `disposition`, `disposition_citation`, `override_ledger`, `carried_disposition(_use)`, `merge_record` |
| 0072–0129 | `dm-periphery` | ledger ×8, `mainline_meas` ×12, fixity ×6, fleet ×4, governance ×7, `mainline_ops` ×5, `predicate_revocation`, the two DM-16 orphans |
| 0130–0199 | `dm-functions-triggers` | ~15 `CREATE FUNCTION` (0130–0159), ~28 `CREATE TRIGGER` (0160–0199) |
| 0200–0279 | `dm-views-rls` | 15 `mainline_audit` views, 4 `mainline_qa` views, ~30 policies, the deferred `exposure_receipt → silence_receipt` FK |

---

## 4. Constraints every worker in this domain obeys

Repeated in every brief because a worker sees only its brief.

1. **One DDL statement per file.** `NNNN_snake_name.up.sql`. The runner does not wrap the body in a
   transaction, so a two-statement file is not atomic and `dirty` becomes undiagnosable.
2. **Mandatory header block** on every file — `MI:`, `I:`, `COUNSEL-GATED:`, `RATIONALE:` — linted.
3. **`CREATE SEQUENCE` is banned.** Sequence updates commit outside the transaction; a gap must *mean* tampering.
4. **Row-level TTL on exactly three tables**, none in schema `mainline`.
5. **`CHECK` sees only the row being written** — no subqueries, no cross-table reads, no `now()`, no
   JSONB operators (DM-4), no UDF-of-column.
6. **`DEFERRABLE INITIALLY DEFERRED` is unimplemented** — every intermediate state must be legal at
   statement boundaries, and the *last* write must be the one that trips.
7. **PL/pgSQL is `IF/ELSIF` plus at most one aggregate `SELECT … INTO`.** No `FOR … IN`, `FOREACH`,
   `PERFORM`, `EXECUTE`, `GET DIAGNOSTICS`, `CASE` statement, `RECORD`, `%TYPE`, `%ROWTYPE`.
   (A `CASE` *expression* inside a statement is fine; `TG_ARGV` is one-based in CockroachDB.)
8. **Vectors live in sidecar tables, one vector index per table, declared inline, table created empty.**
9. **Inverted / GIN indexes**: inverted column last, no `STORING`.
10. **Every projected column carries a comment naming the table it is derived from**, and appears in
    `TRIGGER-MAP.yaml`.
11. **Explicit names on every constraint, index and policy** (DM-10).
12. **Schema-qualify everything.** No `search_path` reliance.

---

## 5. Where the failing tests go

| Tier | Owner | Path | What it proves |
|---|---|---|---|
| 0 | `dm-runner` | `packages/trappoint-migrate/tests/` | runner semantics with no cluster: lint, lock CAS, dirty, protected floor, fingerprint stability |
| 0 | `dm-runner` | `tests/integration/schema/test_mi_ratchet.py` | the catalogue ratchet itself, and the first deliberately-red case (PL-2) |
| 1 | each table worker | `tests/integration/schema/test_mi_<area>.py` | DDL shape from `information_schema`/`SHOW CREATE` + illegal histories with exact SQLSTATE and constraint name |
| 2 | `dm-functions-triggers` | `tests/integration/schema/test_mi_projection.py` | **P2 as a property**: for every `TRIGGER-MAP.yaml` row, a client-supplied value is overwritten, and an absent authoritative row raises the recorded SQLSTATE |
| 3 | `dm-views-rls` | `tests/integration/schema/test_mi_views.py`, `test_mi_rls.py` | ≤25 rows / ≤10 KiB / no system catalog; forced-RLS gate transaction; `mainline_qa` unreachable from the MCP identity |

Isolation primitive is a fresh `site_id` per test against one long-lived cluster (`pytest-xdist`
safe). Migration and RLS suites are `@pytest.mark.schema` and run serialised on a disposable
container, pinned to `cockroachdb/cockroach:v26.2` by digest — never the `testcontainers` default,
which is v24.1.1 and predates triggers.

---

## 6. Risks I am accepting

| # | Risk | Why I accept it | Owning artefact |
|---|---|---|---|
| DR-1 | `GT-06` (inline `VECTOR INDEX` in `CREATE TABLE`) fails | It is the single highest-risk file in the set; the fallback (import-then-index for every environment) is a `CREATE TABLE` + `CREATE VECTOR INDEX` pair in the same band, pre-written | `dm-recall-tables`, migrations 0041–0042 and their `.fallback.sql` siblings |
| DR-2 | `GT-13` (`digest()` in a `STORED` column) fails | Absorbed by DM-5: tests assert behaviour, so the swap is one file | `dm-gate`, `test_mi_gate.py` |
| DR-3 | The `TSVECTOR` computed column or `gin_trgm_ops` index is rejected on v26.2 | Neither is load-bearing for a gate; both degrade to application-side computation and the lexical channel is already explicit SQL tables | `dm-recall-tables`, `dm-spine` |
| DR-4 | S8 lands late and most `MI` tests stay red for the whole build | This is the intended state, and DM-8 makes it visible rather than silent; the failure mode it prevents (green tests that assert nothing) is worse | `mi_catalogue.yaml` ratchet |
| DR-5 | GSAC (DM-2) diverges from what the gate lead and console assume | Mitigated by publishing `GSAC.md` before `dm-gate` writes a line of DDL, and by `dm-runner` landing first | `verticals/mainline/db/GSAC.md` |
| DR-6 | The counsel answer arrives and contradicts the conservative default | Contained to seed data and one TOML by DM-17; the DDL does not move | `ext/disposition_ext/` |
| DR-7 | 79 tables is more surface than one review pass can hold | The header block + `migrations.lock.json` + the MI catalogue make the set *walkable*; the founder's ten-minute regulator read is the rendered kernel SQL, not the vertical's 200 files | `migrations.lock.json` |
| DR-8 | Grants-outside-migrations (DM-7) means a fresh cluster is unusable until `grants apply` runs | Accepted: `trappoint-migrate apply` refuses to report success unless the grant matrix has been asserted in the same invocation, and the privilege-probe test is part of the schema tier | `GRANTS.yaml`, `trappoint-migrate` |

---

## 7. Worker roster

| # | Worker | One line |
|---|---|---|
| 1 | `dm-runner` | The migration runner, the numbering registry, the `MI01–MI30` catalogue, and the red-before-green ratchet that makes PL-2 mechanical. |
| 2 | `dm-foundation` | Schemas, ownership, the seven enum types, the clearance lattice with its three deliberately absent cells, `site`, `person`, `signing_credential`. |
| 3 | `dm-spine` | The repository spine: content-addressed commit DAG, `doc`, `clause`, `clause_version` with BLOODLINE columns, the vector sidecar, and Conservation of Blame Mass's `identity_residue`. |
| 4 | `dm-blame` | The blame DAG and `clause_blame_closure` — append-only, generation-versioned, monotone — plus the recursive-CTE writer as a committed, `EXPLAIN`-asserted statement. |
| 5 | `dm-recall-tables` | The three-table vector split with one index each, the LMB cue entity, the explicit BM25 tables, and the fatality bond set. |
| 6 | `dm-gate` | Both gated subjects, the six named refusals, `blocking_check` with its `dedupe_key`, the exposure receipt, and the GSAC specification everything downstream reads. |
| 7 | `dm-disposition` | The counsel-gated disposition family behind `disposition_ext`, and `merge_record` — the epoch pin, with two MATCH SIMPLE composite FKs. |
| 8 | `dm-periphery` | Ledger, measurement, fixity, fleet, governance, ops — 40-odd tables, the TTL allowlist, and the FK'd `outbox_kind` vocabulary. |
| 9 | `dm-functions-triggers` | The enforcement layer: every `CREATE FUNCTION` and `CREATE TRIGGER`, plus `TRIGGER-MAP.yaml` and the P2 property test that walks it. |
| 10 | `dm-views-rls` | The MCP audit surface sized to its limits, the `mainline_qa` views no MCP account ever reaches, the full RLS matrix including write policies, and the deferred cycle FK. |

---

*Data model lead, 2026-08-05. Ten workers, disjoint bands, seventeen decisions, eight accepted risks.
The domain is done when every `MI` in `mi_catalogue.yaml` reads `enforced`, and not one of them was
ever green before its mechanism existed.*

---

# ⚠ PLATFORM GROUND TRUTH — MANDATORY, SUPERSEDES ANY CONFLICTING ASSUMPTION ABOVE

**Measured against the live cluster on 2026-08-07. See `docs/adr/0002-g1-platform-ground-truth.md`.
These are MEASUREMENTS, not documentation. Where your brief or this plan assumed otherwise, THESE WIN.**

**Cluster:** CockroachDB CCL **v26.2.5**, cluster version 26.2, **Basic tier**, `aws-ap-southeast-1` (**Singapore**).
**Bedrock:** `ap-southeast-2` (Sydney), 8 `au.*` Claude profiles ACTIVE (incl. `au.anthropic.claude-sonnet-5`, `au.anthropic.claude-opus-5`).

## F1 — Vector index WORKS on Basic, but the optimizer will not choose it

`feature.vector_index.enabled` is **`true` by default**. `VECTOR(n)` columns and prefix-column vector indexes **create and populate successfully on the free Basic tier**. The largest platform risk is retired.

**BUT:** at 5,200 rows an unhinted prefix-constrained ANN query does **NOT** use the index — the plan is `top-k → render → filter → scan`. The index is traversed **only** when named explicitly:

```sql
SELECT id FROM tbl@tbl_prefix_emb_idx
WHERE tenant = $1 AND state = $2          -- every prefix column = a single value
ORDER BY emb <=> $3 LIMIT $4
```

**RULING:** every ANN arm **pins the index explicitly**. Any CI assertion of the form "EXPLAIN proves the ANN uses the index" must assert traversal of the **named, hinted** index — an unhinted assertion fails at demo corpus scale. This is also the more deterministic engineering: a plan that flips on table statistics must not sit beneath a safety gate.

The `IN (...)` trap is UNCHANGED: every prefix column must still be constrained to a single value, so an ancestor walk is one hinted ANN query per ancestor, `UNION ALL`-ed and re-ranked.

Tunable session vars confirmed present: `vector_search_beam_size = 32`, `vector_search_rerank_multiplier = 50`.

## F2 — The time-travel window is 75 minutes, not 4 hours

`gc.ttlseconds = **4500**` on this cluster (the architecture assumed 14400). **`AS OF SYSTEM TIME` cannot reach beyond ~1 hour.** All long-horizon versioning is the application-level commit DAG. No demo beat, claim, exhibit or test may depend on time-travel reaching further. Verified live: a query past the window is **refused**, not silently wrong — keep that as a conformance case.

## F3 — Confirmed available (build against these freely)

| Capability | Status |
|---|---|
| PL/pgSQL triggers with `RAISE EXCEPTION` | ✅ PASS |
| **CTE inside a UDF** | ✅ PASS — the "no CTE in UDFs" claim was stale (removed v25.1) |
| `ALTER TABLE … ENABLE ROW LEVEL SECURITY` | ✅ PASS |
| `STORED` computed column with `digest()` | ✅ PASS — the `dedupe_key` fix (finding S5) is implementable |
| Partial `UNIQUE` index | ✅ PASS — the one-custodian invariant is implementable |
| `kv.rangefeed.enabled` | ✅ `true` — changefeeds available |
| `amazon.titan-embed-text-v2:0` in ap-southeast-2 | ✅ PRESENT (closes a previously-flagged unverified item) |
| `cohere.embed-v4:0` in ap-southeast-2 | ✅ PRESENT — not in the original design; a benchmark candidate, not a default |
| Bedrock Rerank in ap-southeast-2 | ❌ ABSENT, as assumed. Take no dependency |

## F4 — `CREATE SEQUENCE` succeeds on this cluster

The CI lint banning `CREATE SEQUENCE` / `nextval(` / `SERIAL` / `unique_rowid()` is therefore **load-bearing, not decorative**. Gap-free-by-CAS is only meaningful while that lint holds.

## F5 — Residency: inference in Australia, database in Singapore

Sydney (`ap-southeast-2`) is **Advanced-tier only** — absent from the Basic and Standard region lists. **Any claim of end-to-end Australian data residency is FALSE for this deployment** and must not appear in the README, submission, video, console, or any comment. State the split precisely wherever residency is mentioned.
