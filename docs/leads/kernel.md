# KERNEL LEAD — TRAPPOINT: the refusal engine

**Domain implementation plan.** Milestone K1 (THE REFUSAL), plus the K1-resident slices of K2
(gap-free CAS sequencing, self-attesting gate). Authority: `ARCHITECTURE.md` §3, §5.0–5.6, §5.11,
§11.2, §16, §18, §19; `BUILD_PLAN.md` §0.2, §2.2, §3 (K1, K2).
Nothing here re-litigates a decision those documents already made. Where they leave a genuine
choice, or contain a residual contradiction, §2 below rules on it and says why in one line.

---

## 0. What this domain must be true of, in one paragraph

The kernel is not a library and not a service. It is **a specification (`spec/`), a set of
deterministic SQL templates (`packages/trappoint-sql`), and a conformance suite
(`packages/trappoint-conformance`)** whose passing is the only meaning of the phrase
"TRAPPOINT-compliant". Everything else in my domain — the migrate runner, the gate client, the
refusal diagnoser, the reference model — exists to make those three artefacts provable. The exit
condition is `G2`: ~45 illegal histories green, each asserting an exact SQLSTATE **and** an exact
constraint name; refusal depth ≥ 2 on every merge-gate history, proven by unwelding; the refusal
taxonomy total over `{40001, 23514, 23503, 23505, P0001}`; `CF-07` green.

---

## 1. Strategy

### 1.1 The substrate is proved at K1, not at K12

**Decision.** The kernel ships a **reference vertical** (`trappoint_ref` schema) alongside the
MAINLINE binding, from day one, inside `packages/trappoint-sql/refvertical/`.

Three things fall out and each is load-bearing:

1. **K1 stops depending on K3.** `fn_check_project` reads an *authority source* — in MAINLINE that
   is `mainline.clause_blame_current`, which is the ancestry lead's migration `0038/0039`. If the
   kernel's conformance suite needed that table, K1 could not be green before K3, which inverts
   the milestone lattice. The reference vertical supplies an isomorphic closure table, so
   `trappoint-conform --profile trappoint-ref` is green on Day 5 with zero ancestry code in
   existence.
2. **The extension mechanism is exercised the day it is written**, not eighteen months later.
   Two bindings that both render is the entire substrate claim; one binding is a template engine
   with an audience of one.
3. **`--profile mainline` is added to CI the day migration `0029 clause_version` lands.** Stated as
   a risk in §5, not hidden.

### 1.2 The Authority Source Contract — P2 enforced at render time

**P2** says any column a gate reads must be written by a trigger from an authoritative source, and
the trigger must `RAISE` when that source is missing. Today that is a discipline. I am making it a
**compile-time refusal**.

`vertical.toml` must declare, for every projected gate column, the relation and columns it is
derived from:

```toml
[[authority_source]]
projects   = ["blocking_check.severity", "blocking_check.virulence", "blocking_check.closure_gen"]
relation   = "mainline.clause_blame_current"
key        = ["clause_uuid", "as_of_commit"]
columns    = ["max_severity", "virulence", "closure_gen"]
on_missing = "raise"          # the ONLY legal value
```

`trappoint render` **refuses to emit** a gate template whose projected column has no
`authority_source` entry, and refuses any entry with `on_missing != "raise"`. The adversarial
review's build-blocking finding S1 becomes a build error rather than a code review. This is ours
and it is cheap: about sixty lines in `binding.py`.

### 1.3 Red before green, mechanically

`PL-2` is not satisfied by "we wrote tests first". It is satisfied by a CI job that **was observed
red**. Sequencing:

- W2 lands `db.yml` with a CockroachDB service container, the conformance runner, and `CF-01`
  (`merge a permit carrying one open blocking check` → expect `23514` on
  `gate_closed_when_issued`) **against an empty database**. The job is red. That commit is the
  proof artefact; its run URL goes into `docs/adr/0005-red-before-green.md`.
- Every subsequent DDL/trigger worker turns exactly the cases named in its brief from red to green
  and may not touch a case it does not own.
- W9 owns the case corpus and asserts, in `test_manifest_totality`, that every `CF-*` in
  `spec/conformance/manifest.toml` has an implementation and every implementation has a manifest
  entry. A case that exists in neither place cannot silently vanish.

### 1.4 The two projection triggers are the first SQL in the repository

`fn_check_project` and `fn_disposition_project` are written before anything depends on them
(BUILD_PLAN Day 4). In this decomposition that means W6 cannot start until W4 and W5 have landed
the tables, but W6 is the **first** worker whose output is a behavioural claim, and `CF-07` — the
only test of the claim the company is built on — is the first case W9 is required to make green.

### 1.5 Refusal is a product surface, not an exception

Three artefacts, all consumed:

- `spec/errors.md` — the SQLSTATE contract. `40001` retryable; `23514 / 23503 / 23505 / P0001`
  refusals, attempted **exactly once, ever**; anything else is a suite failure.
- `spec/wire/refusal.md` — the refusal payload JSON schema: `{constraint, sqlstate, mus[], naa{},
  subject, gate_epoch, evidence}`. The console, the ledger and the conformance runner all parse it.
- `packages/trappoint-diagnose` — **QUICKREFUSE**: the minimal unsatisfiable subset and nearest
  admissible alternative, computed with the **database itself as the MUS oracle**. Declarative
  decomposition first (counters → witness rows, deterministic, sub-millisecond); QuickXplain over
  `SAVEPOINT` / `ROLLBACK TO SAVEPOINT` probes as the general algorithm for composite refusals the
  decomposition does not cover. CockroachDB supports general-purpose nested savepoints, so the
  probe loop is legal; it runs in a *separate* read-mostly transaction so a refusal diagnosis can
  never itself mutate the gate.

  Novelty note: MUS extraction is a solved problem *with a SAT/SMT solver*. Using an RDBMS's own
  constraint engine as the oracle — so the explanation is produced by the same mechanism that
  produced the refusal, and therefore cannot disagree with it — is the part with no prior art I
  could find. It is also the answer to "a gate that only says no gets routed around."

### 1.6 Unwelding is mutation testing applied to invariants

`packages/trappoint-conformance/unweld/` runs `ALTER TABLE … DISABLE TRIGGER` and
`ALTER TABLE … DROP CONSTRAINT` **one mechanism at a time** on a disposable single-node container,
re-runs the illegal history, and asserts it **still fails**. Output: `REFUSAL_DEPTH.md`, a matrix
of history × surviving mechanism. CI fails if any merge-gate history has depth < 2. This is the
only place the structural-redundancy claim is made (S4) — at runtime the deterministic `RAISE`
fires first, and the corpus must never claim otherwise.

Pre-committed response to depth 1: **cut the mechanism, do not ship it.** A single-welded gate is
a claim that cannot be made under oath.

### 1.7 Sequencing and what is proven before what

```
W1 spec ──┬──► W2 toolchain + RED ──┬──► W3 render + foundation DDL (0001–0023)
          │                          │
          └──────────────────────────┴──► W4 subject & pin DDL (permit, CR, events, merge_record)
                                              │
                                              ▼
                                          W5 obligation & clearance DDL (blocking_check … disposition)
                                              │
                                              ▼
                                          W6 projection functions + triggers   ← CF-07 becomes possible
                                              │
                                              ▼
                                          W7 merge procedures + gate triggers + trappoint-core
                                              │            (taxonomy, discriminating retry, CAS)
                                     ┌────────┼────────┐
                                     ▼        ▼        ▼
                                  W8 QUICK-  W9 corpus  W10 reference model
                                  REFUSE     + unweld   + Hypothesis + concurrency
```

Proof order, strictly: **projection before obligation** (a check whose severity is an input is not
a check) → **pin before merge** (a merge that can be re-opened is not a merge) → **refusal before
diagnosis** (a diagnosis of a refusal that did not happen is a fiction) → **differential last**
(the reference model is only meaningful once the real gate has a shape to disagree with).

---

## 2. Decisions and corrections (one line of justification each)

Ten rulings. Six are choices the documents left open; four are corrections to residual drift in
`ARCHITECTURE.md` that would otherwise ship as bugs.

| # | Ruling | Why |
|---|---|---|
| **D1** | **`merge_record` carries nullable `permit_id` and `cr_id` plus two composite FKs; the "partial-FK pair" of §5.5 is MATCH SIMPLE semantics, made explicit.** `subject_id` stays `NOT NULL` and is bound by `CHECK (subject_id = COALESCE(permit_id, cr_id))`. | CockroachDB has no conditional FK; a composite FK with any NULL column is not enforced, which is exactly the "one per kind" behaviour the architecture describes and never spells out. |
| **D2** | **`disposition` and `override_ledger` become subject-polymorphic** — `subject_kind` + nullable `permit_id`/`cr_id` + `CHECK ((permit_id IS NULL) <> (cr_id IS NULL))`, mirroring `blocking_check`. | §5.5 gives `disposition.permit_id NOT NULL`, which predates S16; as written, a change request that trips `weaken_over_blood` can never be dispositioned and MI30 turns the repository into a brick wall. |
| **D3** | **A missing `clearance_legal` row does NOT `RAISE 23503`.** `fn_disposition_project` sets the projected requirement columns to their **strictest** values (`req_* = true`, `min_signer_rank = 9`) and returns `NEW`; the real composite FK `fk_clearance` then fires `23503` **with its constraint name**. | A synthetic `23503` carries no constraint name, and the constraint name is the exhibit. Also avoids `23502` (a NOT NULL projection left unset), which is outside the taxonomy. |
| **D4** | **No `CASE` expression in any PL/pgSQL body.** Counter arithmetic uses boolean casts: `unmet_floor_count + (NOT NEW.reading_floor_met)::INT8`. | `GT-13` has not answered whether a `CASE` *expression* is legal inside a PL/pgSQL statement; `PL-3` forbids a dated path on an unproven capability, and the cast form is unconditionally legal. |
| **D5** | **Every capability under a `GT-*` check is a render-time switch, not a runtime branch.** `binding.capabilities.stored_digest` (GT-13) selects `dedupe_key … STORED` vs a client-computed `BYTES` column with a length `CHECK`; `binding.capabilities.triggerdef` (GT-05) selects `pg_get_triggerdef()` vs `SHOW CREATE TABLE`. `trappoint render` refuses to run without a `g1-attestation.json` naming each capability `PASS` or `FALLBACK-SELECTED`. | `PL-3` made mechanical: an unverified capability cannot reach a rendered migration, and the fallback is committed SQL a reviewer can read rather than a branch a reviewer must trust. |
| **D6** | **`trappoint migrate` owns a `trappoint` bootstrap schema** (`schema_migration`, `schema_lock`, `schema_attestation`) created by `trappoint migrate bootstrap`, outside the numbered sequence. Kernel procedures live in the same schema (`trappoint.merge_permit()`). | Keeps §18's numbering clean, gives CockroachDB the real lock table it needs (no advisory locks), and matches the architecture's own `trappoint.merge_permit()` naming. |
| **D7** | **§18 numbering is preserved; a slot that needs more than one statement gets a lowercase letter suffix** (`0071a_merge_record.sql`, `0071b_epoch_pin_permit.sql`). The runner orders lexicographically on the full filename. | One statement per file is non-negotiable (a multi-statement file is not atomic and `dirty` becomes undiagnosable); renumbering §18 would break every cross-reference in the corpus. |
| **D8** | **The function range extends to `0100–0119` and the trigger range to `0120–0149`.** | §18 sized `0100–0114` before `merge_change_request()`, `explain_refusal()` and the CAS append helper existed; extending an open range costs nothing and renumbering costs everything. |
| **D9** | **`fn_check_materialised`'s outbox insert is conditional on `binding.emit_outbox`.** The reference vertical sets it false. | The substrate must not hard-depend on a changefeed table it does not own; `mainline_ops.outbox` is migration `0099` and belongs to another lead. |
| **D10** | **`CREATE SEQUENCE` is banned by a CI guard, not by convention**: `trappoint migrate lint` greps every migration and every rendered template and fails on `CREATE SEQUENCE`, `nextval(`, `SERIAL`, `unique_rowid()`. | The gap-free-by-CAS claim is worthless if one future migration reintroduces a sequence; a sequence gap must **mean** tampering. |

---

## 3. Interfaces this domain publishes

| Interface | Consumer | Owner |
|---|---|---|
| `spec/TRAPPOINT-SPEC.md` + `spec/invariants/I01..I16.md`, SemVer'd (adding an invariant = MAJOR) | every vertical, the upstream skill, the README | W1 |
| `spec/errors.md` — the SQLSTATE contract | `trappoint-core.gate`, the console, the refusal ledger | W1 |
| `spec/wire/refusal.md` — the refusal payload JSON schema (MUS + NAA) | console, ledger relay, conformance runner | W1 |
| `spec/conformance/manifest.toml` — `CF-id → invariant → SQLSTATE → constraint name → anomaly` | the runner, `ANOMALY_COVERAGE.md`, `REFUSAL_DEPTH.md` | W1 |
| `spec/binding/vertical.schema.json` — what a `vertical.toml` must contain | every vertical, `trappoint render` | W1 |
| `trappoint render` / `trappoint render --check` | CI zero-diff assertion, every vertical | W3 |
| `trappoint migrate {bootstrap,up,status,attest,lint}` | CI, the provisioning agent, the cloud lead | W2 |
| `trappoint_core.gate.execute_gate()` / `GateRefused(constraint=…)` | `mainline-gate-svc`, the console API | W7 |
| `trappoint.merge_permit()` / `trappoint.merge_change_request()` (pgwire `CALL`) | the gate service | W7 |
| `trappoint_diagnose.explain(refusal) -> RefusalPayload` | the gate service, the console | W8 |
| `trappoint-conform --dsn … --profile {mainline,trappoint-ref}` | `G2`, every future vertical, the OSS claim | W9 |

**Import-linter contracts (four, W2 owns the file):** the Apache substrate never imports the FSL
vertical · no model code path in `trappoint_core` or the gate service · the offline verifier stays
dependency-minimal · **no blanket-retry helper exists anywhere** (`tenacity`, `backoff`, `retrying`
are forbidden modules repo-wide).

---

## 4. Worker roster

| # | id | One-line purpose |
|---|---|---|
| 1 | `spec-invariants` | The SemVer'd public API: I01–I16, the SQLSTATE contract, the refusal wire schema, the machine-readable conformance manifest, the vertical binding schema. |
| 2 | `toolchain-and-red` | `trappoint migrate` (forward-only, lock table, dirty marker, schema attestation), the workspace root, the four import-linter contracts, and **the CI job observed red before any schema exists**. |
| 3 | `render-and-foundation` | `trappoint render` with the Authority Source Contract check, both bindings (MAINLINE + reference vertical), and migrations 0001–0023: schemas, roles/grants, types, `subject_transition`, `clearance_legal`, `person`, `signing_credential`. |
| 4 | `subject-and-pin` | The PIN half: `permit`, `change_request`, `permit_clause`, `cr_clause`, `permit_event`, `cr_event`, `merge_record` and the two epoch-pin composite FKs — including the six named refusal `CHECK`s. |
| 5 | `obligation-and-clearance` | The obligation half: `blocking_check` with the `dedupe_key` digest, `exposure_receipt`/`exposure_line`/`receipt_expiry`, `defeater_option`, `disposition` with `fk_clearance` and `fk_exposure`, `disposition_citation`, `override_ledger`. |
| 6 | `projection-triggers` | PROJECT: `fn_check_project`, `fn_disposition_project`, `fn_check_materialised`, `fn_disposition_close`, `fn_disposition_retract_only`, `fn_permit_event_chain`, `fn_refuse_mutation`, `fn_closure_guard`, `fn_site_role` and their triggers. |
| 7 | `merge-gate-and-core` | REFUSE: `trappoint.merge_permit()` / `merge_change_request()`, the two merge-gate triggers, and `trappoint-core` — the discriminating retry loop, `GateRefused`, and the gap-free CAS ledger append. |
| 8 | `quickrefuse` | The minimal unsatisfiable subset and nearest admissible alternative: declarative decomposition + QuickXplain over savepoint probes, the `refusal_ledger` table, and the wire payload emitter. |
| 9 | `conformance-corpus` | The ~45 illegal histories with exact SQLSTATE **and** constraint name, the unwelding matrix, `ANOMALY_COVERAGE.md`, `REFUSAL_DEPTH.md`, and the self-attesting-gate snapshot test. |
| 10 | `reference-model` | ~150-line pure-Python oracle, the Hypothesis `RuleBasedStateMachine` differential, the shrinkable interleaving scheduler, the `READ COMMITTED` differential, and the N-parallel-merge concurrency job. |

---

## 5. Risks I am accepting

1. **`--profile mainline` cannot be green until the ancestry lead lands `0029 clause_version` and
   `0038/0039 clause_blame_closure`.** `G2` is therefore declared on `--profile trappoint-ref`
   green plus `--profile mainline` green-when-unblocked, and the README says so. Mitigation: the
   Authority Source Contract means the mainline binding is a five-line `vertical.toml` change, not
   a code change.
2. **Trigger maturity.** Triggers are GA at v26.2 but young; the trigger graph is kept acyclic and
   depth 1 by construction, and W9's unwelding suite is the detector for a trigger that silently
   stops firing.
3. **`GT-05` (`pg_get_triggerdef()`) and `GT-13` (`digest()` in `STORED`) are unanswered on
   2026-08-05.** D5 turns both into render switches with committed fallback SQL. If `GT-13` fails,
   `dedupe_key` and `chain_digest` become client-computed and the "server computes the chain, the
   inserter cannot lie" sentence weakens to "the trigger verifies the chain the inserter supplied"
   — which `fn_permit_event_chain` already does, so the invariant survives and only the prose
   changes.
4. **Early binding on stored procedures (v26.2).** `CREATE PROCEDURE` resolves references at
   creation time, so any table-shape change requires `CREATE OR REPLACE PROCEDURE` in the same
   migration. W9's `pg_get_functiondef` snapshot test is the tripwire.
5. **QuickXplain's oracle costs a probe transaction per call.** Accepted because it runs only on
   the refusal path, never on the merge path, and the declarative decomposition covers every
   single-counter refusal without a probe.
6. **`uv.lock` is the one shared generated file.** Owned by W2 for creation; any worker adding a
   dependency declares it in its own package `pyproject.toml` and re-runs `uv lock`. Conflicts are
   resolved by re-running the command, never by hand-editing.
7. **`CF-22` (the whole gate transaction under `FORCE ROW LEVEL SECURITY`) depends on the security
   lead's policies at `0159–0170`.** W9 writes it to skip-with-reason while `pg_policies` is empty
   and hard-fail once it is not, so it can never quietly pass by absence.

---

*Kernel plan, K1. The deliverable is a refusal. A suite that has never been red asserts nothing.*

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

## F6 — A LOCAL CockroachDB node is running, and it DIVERGES from Cloud in one way that matters

A local node is up for the fast red/green loop, pinned to the **exact Cloud version**:

```
docker run -d --name mainline-crdb -p 26257:26257 -p 8080:8080 \
  cockroachdb/cockroach:v26.2.5 start-single-node --insecure --store=type=mem,size=2GiB
```
**Local DSN:** `postgresql://root@localhost:26257/defaultdb?sslmode=disable` (insecure, in-memory, no TLS).

Measured parity with Cloud: `v26.2.5` OK · `feature.vector_index.enabled = true` OK · vector index creates OK · **hinted** prefix-constrained ANN traverses the index OK (unhinted still does not — F1 stands).

**Performance:** DDL + 5,000 vector inserts took **2.4 seconds locally** vs **>120 seconds for 9 DDL statements** on Cloud Basic. Run the conformance suite, unwelding harness, concurrency tests and property tests **locally**. Cloud is the nightly `cloud-verify` truth check, not the inner loop.

### THE DIVERGENCE — `gc.ttlseconds`

| | Cloud Basic | Local default |
|---|---|---|
| `gc.ttlseconds` | **4500** (75 min) | **14400** (4 h) |

**Local is MORE PERMISSIVE than production.** A time-travel test that passes locally can fail on Cloud.

**`compose.yaml` (owned by `kernel/toolchain-and-red`) MUST apply `ALTER RANGE default CONFIGURE ZONE USING gc.ttlseconds = 4500` in an init step**, so every developer and every CI run gets Cloud-truthful behaviour by construction rather than by remembering. Standing rule: where local and Cloud differ, configure local to the **stricter** value.
