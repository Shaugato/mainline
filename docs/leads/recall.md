# RECALL — the diachronic gate

**Lead plan. Domain: retrieval that decides whether a permit may merge.**
Authority: `ARCHITECTURE.md` §5.4, §5.5, §5.7, §5.11, §6, §9.2, §16 (MI16–MI18), §18 · `BUILD_PLAN.md` K4 · `research/05-architecture/diachronic-recall.md`.
Licence boundary: `packages/trappoint-recall/*` is Apache-2.0 substrate (no MAINLINE domain vocabulary, no `mainline_*` imports); `verticals/mainline/packages/mainline-recall-agent/*` is FSL-1.1-ALv2.

---

## 0. The one sentence

Recall is not a search box: it is the function that turns *"which incidents wrote the controls this permit is about to waive"* into an integer on `permit.open_blocking`, and the whole domain exists to make that integer **defensible in both directions** — a miss is a fatality exhibit, a false positive is a rubber stamp.

## 1. Strategy: the empirical bet is settled before the stack is built

`P@block ≥ 0.75` at `Retro-Recall@3 ≥ 0.90` is a **hypothesis**, not a design. The build order therefore inverts the intuitive one:

```
harness (RED)  →  corpora + gold sets  →  providers  →  cue synthesis  →  taxonomy/LMB
                                                              ↓
                        DDL + projection triggers  →  ANN arms  →  BM25  →  fusion/admission
                                                              ↓
                                              orchestrator + PER + CUE HORIZON + THYMOGATE
```

**PL-2 red-before-green is enforced structurally.** Worker `recall-eval-harness` ships `tests/eval/recall/test_g4alpha_gates.py` — four assertions (`Retro-Recall@3` on severity-5, `P@block`, nuisance rate, mean blocking checks/permit) plus the silence conservation law — that **must be red on first commit** and are made green one channel at a time. A suite that has never been red asserts nothing about a product whose deliverable is a refusal.

**Ablation is a deliverable, not a nicety.** `A → +B → +C → +C&D → +rerank → +SGA`, cue-vs-narrative embedding, prefix on/off, 1024-d vs 256-d, beam sweep. The table is simultaneously the hackathon artefact and the diligence artefact, and it is the only honest way to answer *"why is any of this here?"* per component.

**Every number ships with a Wilson lower bound and the split policy that produced it.** Point estimates are banned from `docs/`, the README and the deck by CI grep (`scripts/recall/no_bare_point_estimates.py`, owned by the harness worker).

## 2. Decisions made here (the documents left these open)

| # | Decision | One-line justification |
|---|---|---|
| **D1** | **The prefix columns of `event_cue_embedding` / `event_cue_coarse` are PROJECTIONS, not inputs.** A `BEFORE INSERT` trigger overwrites `site_id`, `scope_id`, `facet` from the parent `event_cue` row and `RAISE`s when it is absent; `event_cue_coarse.severity_gate` is projected from `event.severity_gate`. | S1 one hop upstream: if an inserter chooses the prefix it chooses the K-means tree, and a fatality filed into the wrong tree is unreachable *forever* with no refusal anywhere. TRAPPOINT P2 applies to the index partition, not only to the gate scalar. |
| **D2** | **The cap of ≤3 blocking checks applies only to `origin='recall_probabilistic'`.** Channels A and B are uncapped. | Otherwise the cap and `bonded_fatalities_all_blocking` (MI16) are contradictory constraints and the gate becomes unsatisfiable on a fonds with four fatalities. |
| **D3** | **Embedded text is a fixed template, not the cue alone:** `"{activity_path} \| {asset_class} \| {facet}: {cue_text}"`, identical on the event side and the permit side. The template string is versioned in `prompt_version` and its sha256 is in `recall_policy.calibration_set_sha256`'s sibling digest. | Contextual retrieval is the cheapest available win, and query/document genre symmetry is the entire reason cues exist. If the template drifts between sides, the whole design silently degrades to narrative search. |
| **D4** | **Offline embedding provider = `BAAI/bge-large-en-v1.5`** (MIT, native 1024-d, pinned revision sha). Coarse 256-d for that provider comes from a **committed PCA matrix**, not Matryoshka truncation. Bedrock provider = `amazon.titan-embed-text-v2:0` at 1024-d with Matryoshka truncation to 256-d and client-side renormalisation. | AWS credentials are not yet valid; the harness and `just demo-local` must run with no cloud account. bge-large is 1024-d natively so the DDL is unchanged. bge is **not** MRL-trained — truncating it would be a false claim, so PCA it is. `embed_model` distinguishes them and the harness refuses to score a mixed corpus. |
| **D5** | **Reranker and cue synthesiser = Claude on the Bedrock `au.*` cross-region inference profile** (residency, pinned by ARCHITECTURE §6.4 — Bedrock Rerank is absent from `ap-southeast-2`). First-party id `claude-opus-5`; the Bedrock id / inference-profile ARN is **resolved at runtime** via `bedrock:ListInferenceProfiles` and pinned into `recall_policy`, never hard-coded. | PL-3: no unproven capability on a dated path. The profile ARN is a day-1 check (`GT-RC-01`), and until it passes the cassette provider serves CI and the demo. |
| **D6** | **Structured output = `output_config.format` (`json_schema`, `additionalProperties:false`, `strict:true`) plus client-side Pydantic validation.** One retry with the validator error appended, then dead-letter. A dead-letter writes `silence_ledger(reason='abstained')`. | Matches ARCHITECTURE §8.4's structured-output contract; `abstained` already exists in the closed D10 vocabulary, so no schema change. Never a free-text retry loop — that is how a silent extraction failure becomes a silent memory gap. |
| **D7** | **Prompt caching on the listwise judge:** the rubric + facet definitions + few-shots are a byte-frozen system prefix with `cache_control` on the last system block; candidates go in the user turn *after* the breakpoint. A cassette-replay test asserts `cache_read_input_tokens > 0` on call #2. | The rerank dominates the S4 budget (4 s p50 / 20 s p95). Caching is the only lever that does not cost accuracy, and an un-asserted cache is usually a broken cache. |
| **D8** | **The calibrator is serialised as monotone step-function knots in `recall_policy.calibrator JSONB`** (new column), never as a pickle. | A pickle is neither auditable nor safe to load, and `p_relevant` is an exhibit. Knots are re-evaluable by a stranger with 20 lines of code. |
| **D9** | **τ per severity = `max(LTT_τ, precision_floor_τ)`.** Learn-then-Test/CRC gives the recall-side bound; the precision floor is derived from the nuisance ceiling. | CRC assumes exchangeability and safety corpora drift. Taking the max means a recall-driven τ can never breach the nuisance ceiling — *"a rule that breaches the ceiling is rejected rather than tuned"* becomes arithmetic instead of a promise. |
| **D10** | **PER leaf = `sha256(0x00 ‖ JCS({ord, event_id, score_q, tau_applied, outcome}))`, `score_q = round(p_relevant × 10⁶)` as an integer**; nodes `sha256(0x01 ‖ L ‖ R)` (RFC 6962 domain separation, matching the custody ledger's convention). | Float formatting must never be able to break sortedness or reproducibility; the boundary proof's whole force is *"no item can be hand-excluded without breaking sortedness."* |
| **D11** | **Arm set is bounded at 16** (levels 1–3 × populated facets, plus the coarse sweep). Overflow writes `silence_ledger(reason='cap_exceeded')` and sets `recall_run.arms_degraded`. | `optimizer_span_limit` is a silent cliff and an unbounded arm set is how you walk off it. A bounded set with a logged overflow is honest; an unbounded one is a latent full scan. |
| **D12** | **The Retro-Recall time wall is enforced by predicates (`occurred_at < t AND ingested_at < t AND corpus_commit ≤ t`), never by `AS OF SYSTEM TIME`.** | `gc.ttlseconds` defaults to 4 h — AOST cannot reach months back. A harness that silently used AOST would either error or, worse, quietly evaluate on a 4-hour window. |
| **D13** | **Sublinearity is asserted numerically:** per-arm p50 latency across a 5k → 10k → 20k cue corpus must satisfy `t(2n)/t(n) < 1.7` on a 3-run median. | A silently unused index scales linearly regardless of how the plan text is formatted; a ratio is falsifiable, "looks fine" is not. |
| **D14** | **THYMOGATE (M5) lives with the harness, not the retriever.** The panel is a corpus artefact (`tests/fixtures/recall/thymogate_panel.json`); the certificate is emitted by a harness run; `recall_policy.thymogate_certificate_id` is nullable at K4 and becomes `NOT NULL` at K8. | Negative selection *is* an evaluation. Modelling it as a retriever feature would let a tuned retriever certify itself. |

## 3. Interfaces (what other leads may rely on)

- **Recall never writes `blocking_check`.** The orchestrator POSTs a candidate set to the kernel's `POST /v1/permits/{id}/checks:materialise`. Contract: `packages/trappoint-recall/src/trappoint_recall/run/contract.py` (`CandidateSet`, `Candidate`, `ExposureCueRef`) — frozen Pydantic models + a generated JSON Schema. The kernel lead owns the endpoint; I own the payload shape.
- **Migration numbers reserved by recall:** `0040–0046`, `0080–0089`, functions `0110–0114`, triggers `0136–0139` — **confirmed unchanged by the binding ruling at the end of this document (2026-08-08); the function band now starts at `0110` because `fn_candidate_project` moved there out of the trigger band.** The remaining `mainline_meas` tables in §18 renumber to `0089`/`0089a`–`0089z` and stop there; `0090` belongs to `datamodel/dm-periphery`. Two new columns on `recall_policy` (`calibrator JSONB NOT NULL`, `thymogate_certificate_id UUID NULL`).
- **Two new tables** beyond §5.7: `mainline_meas.thymogate_certificate` (M5) and `mainline_meas.recall_certificate` (M4 CUE HORIZON, carrying `index_fingerprint`, `index_generation`, `verdict IN ('complete','partial','UNDETERMINED')`).
- **Consumed, not owned:** `mainline.activity_node`, `mainline.event`, `mainline.event_edge`, `mainline.control_failure`, `mainline.clause_blame_current`, `mainline.permit_slice` (ancestry/ingest leads). If `activity_node` is not yet migrated, worker 5 runs against a fixture DDL in `tests/fixtures/recall_taxonomy/` and the integration lane is skipped, never faked.
- **`mainline_audit.v_recall_conservation` and `v_silence_summary` are the MCP lead's to write.** I own the tables and publish the column contract in `packages/trappoint-recall/src/trappoint_recall/run/views_contract.md`.

## 4. What PER does and does not prove — bound into every artefact

> Proof of Exhausted Recall establishes that **every candidate the retrieval returned and scored below θ is accounted for**, that the score-sorted set was not hand-edited, and that τ was fixed before the run under an anchored policy. It does **not** prove exhaustion of the corpus: C-SPANN is approximate and its trees mutate on every insert. `index_generation` and `index_plan_digest` are in the receipt for exactly this reason.

This sentence is a CI-grepped string in `spec/wire/candidate-commitment.md`, the README and the exhibit renderer. A proof that overclaims is worse than none.

## 5. Worker roster

| id | purpose (one line) |
|---|---|
| `recall-eval-harness` | The RED gate: metrics with Wilson bounds, temporal splits, ablation runner, and the four G4α assertions that must fail on day one. |
| `recall-corpora-goldsets` | MSHA/CSB ingestion and the four gold sets (G1 citations, G2 codes, G3 adjudicated, G4 retro time-wall) plus the routine-permit negative control and the THYMOGATE panel. |
| `recall-providers` | Embedding and judge adapters — Titan v2 / bge-large, `au.*` Claude, cassettes, prompt caching, structured output — so the whole domain runs with no AWS account. |
| `recall-cue-synthesis` | Recurrence-Condition Cues: four facets + narrative, per-facet `insufficient_evidence`, anchor-gazetteer rejection, emitted symmetrically for events and permits. |
| `recall-taxonomy-lmb` | Functional taxonomy induction with a frozen ICMM level 1, and the Level-Materialised Bond writer that makes one arm per ancestor both correct and necessary. |
| `recall-ddl-triggers` | Every recall table, and the projection triggers that make the vector-index prefix and the sweep's severity unforgeable. |
| `recall-ann-arms-explain` | The `UNION ALL` arm generator and the three-layer proof that the vector index was actually used — plus the upstream CockroachDB skill. |
| `recall-lexical-bm25` | Explicit BM25 in SQL over identifier-preserving tokens, because `ts_rank` has neither IDF nor length normalisation and `K-401` is the whole job. |
| `recall-fusion-admission` | RRF → MMR → listwise rerank rubric → isotonic calibration → Severity-Graded Admission → cap, as pure functions with a frozen feature spec. |
| `recall-orchestrator-per` | The run loop that writes `recall_run`/`recall_candidate`/`silence_*`, the PER commitment, the CUE HORIZON certificate, and the degraded A+B path that still blocks. |

## 6. Risks accepted

1. **The bet may lose.** If `P@block` sits below 0.75 on G3, the pre-committed response is **DEMOTE**: channels C and D become advisory-only (a `recall_policy` row, not a migration) and the gate runs on A+B. Smaller true claim over larger unmeasured one.
2. **Cues may not beat contextualised narratives in this domain.** Mitigated by building both and letting the ablation decide; `narrative` ships as a facet, not as a fallback bolted on later.
3. **Taxonomy re-induction changes what the gate would have recalled.** Not solved — mitigated by freezing level 1 to the buyer's ICMM MUE register, versioning every bond with `taxonomy_ver`, and treating re-induction as a commit. Stated as unverified.
4. **MSHA Part 50 narratives are `VARCHAR2(384)`.** Terse coded records make weak `recurrence_test` facets; the rich material is in the fatality investigation PDFs. G1/G4 therefore depend on the PDF corpus, and G2 (codes) trains the calibrator but never appears as a headline number.
5. **No bit-identical ANN replay exists.** We persist the candidate set with scores rather than promising replay of the search. Listed as unverified in the README.
6. **Every number at K4 is preliminary.** No customer-grade floor is claimed at the hackathon checkpoint; the claim is the *harness*, the *arithmetic* and the *refusal*, not the score.

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

---

# MIGRATION RECONCILIATION RULING — 2026-08-08, BINDING, SUPERSEDES THE BANDING SECTION ABOVE

<!-- ────────────────────────────────────────────────────────────────────────────────────
     THIS BLOCK IS REPRODUCED WORD FOR WORD IN FIVE LEAD PLANS:
       docs/leads/kernel.md · datamodel.md · algorithms.md · recall.md · custody.md
     Everything down to "END OF THE COMMON BLOCK" is byte-identical in all five by
     construction. If you are holding a copy that differs from another copy, the
     difference IS the error — go to the source, not to the copy.

     Source of truth for this ruling : docs/leads/migration-reconciliation.md
     Machine-readable authority      : verticals/mainline/db/migrations.allocation.toml
     Generated manifest of the tree  : verticals/mainline/db/migrations.lock.json
     ──────────────────────────────────────────────────────────────────────────────────── -->

**Why this block exists, in one paragraph.** Two domains independently implemented the same
section of the migration order, under two conventions and at two granularities, because two lead
briefs were given overlapping ownership of the migration number space. One side declared ownership
as numeric *bands* (`0050–0065`), the other as literal *file paths* (`0006a_role_migrator.sql`).
The pre-dispatch collision check compared those two declarations as strings, found nothing in
common, and reported **zero collisions**. It was wrong by twenty numbers, and the tree it produced
would not `discover()` at all. Nothing below is a style preference. Each ruling is the mechanical
form of a failure that has already happened once, and each is enforced by a command rather than by
a reader's memory.

**This block does not touch the PLATFORM GROUND TRUTH findings (F1–F6) at the end of this
document. Those are measurements against v26.2.5 and they still win over everything, including
this.**

## MR-1 — the seam: RENDERED or AUTHORED, decided by OBJECT

> **`verticals/mainline/db/migrations/` has exactly two kinds of file, and every number in the
> sequence belongs to exactly one of them: RENDERED (emitted by a template in
> `packages/trappoint-sql/templates/`, never hand-edited) or AUTHORED (written directly in the
> vertical, never emitted). The seam is drawn by OBJECT, not by worker and not by band, and the
> object test is: _would a second TRAPPOINT vertical need this object to pass `trappoint-conform`?_
> If yes it is SUBSTRATE and it is a template. If no it is VERTICAL and it is authored.**

Apply the test to the object, not to yourself. "I am a kernel worker" and "I am a datamodel
worker" are not inputs to it; `permit` is substrate whoever types it, and `site` is vertical
whoever types it. MR-2 fixes the substrate list — the five schemas; the nine roles and the
privilege floor; the seven enum types; `subject_transition` (+seed); `clearance_legal` (+seed);
`person`; `signing_credential`; `permit`; `change_request`; `permit_clause`; `cr_clause`;
`permit_event`; `cr_event`; `blocking_check`; `exposure_receipt`; `exposure_line`;
`receipt_expiry`; `defeater_option`; `disposition`; `disposition_citation`; `override_ledger`;
`merge_record` + its two epoch-pin FKs; `refusal_ledger`; the projection function/trigger family;
the merge procedures and merge-gate triggers; the gap-free CAS append function — and **everything
else in MAINLINE is VERTICAL.**

Three consequences that are not negotiable:

1. **A rendered file is never deleted to resolve a collision — the next `trappoint render`
   recreates it.** The kernel side of every collision in this incident was rendered output; it was
   never hand-written into the migrations directory. A plan that says "delete the kernel's
   `0006a…0006i`" is a plan that fails on the next render.
2. **A hand-authored twin of a rendered file is permanently red, and red in the worst way.**
   `trappoint render --check` is a zero-diff assertion; a twin under a different suffix is not a
   diff, so `--check` stays green while the *runner* refuses the tree. CI green, deploy dead.
3. **A change to a rendered file is a change to its template, followed by a re-render of BOTH
   bindings** (`verticals/mainline/vertical.toml` and
   `packages/trappoint-sql/refvertical/vertical.toml`). Two bindings that both render is the entire
   substrate claim; one binding is a template engine with an audience of one.

## MR-5 — THE ONE FILENAME CONVENTION

```
NNNN[a-z]_lower_snake_slug.sql
```

Stated exactly:

* **`NNNN`** — exactly four decimal digits, zero-padded, allocated by the table in §3/§4 of
  `docs/leads/migration-reconciliation.md` and by its machine-readable form
  `verticals/mainline/db/migrations.allocation.toml`.
* **`[a-z]`** — an optional **single** lowercase letter. Ordering is lexicographic on the whole
  stem, so `0006a < 0006b < 0007` and `0119a < 0120`. It has exactly two legal uses:
  1. **Multi-statement slot.** One logical object that needs more than one top-level statement:
     `0058_blocking_check.sql` then `0058a_bc_open_index.sql`.
  2. **Band overflow.** A full band absorbs new work by suffixing its own last number rather than
     renumbering a neighbour: `0119a_fn_explain_refusal.sql` when `0120` belongs to someone else.
     *This is the mechanism that prevents this incident from recurring: a worker that runs out of
     numbers suffixes, it never borrows.*
  * `x` is reserved for comment/marker-only files (`0009x_covenant_comment.sql`) and sorts last.
* **`_lower_snake_slug`** — `[a-z0-9_]+`. **No second dot, ever.** `.fallback.sql`, `.variant.sql`,
  `.v2.sql` fail `_VERSION_RE` and make the entire directory undiscoverable (measured: one such
  filename made `trappoint migrate` refuse all 121 files beside it). Capability variants live in
  `verticals/mainline/db/ext/<topic>/` and are selected by a render-time switch (kernel D5), never
  by a file in the apply path.
* **Exactly one top-level SQL statement per file.** Enforced by `statement_count()`.
* **`.sql` and nothing else.** There is **no down-migration counterpart and there never will be**:
  `discover()` raises on `.down.sql`, and DM-14 forbids one at or below the protected floor.
  **`.up.sql` is therefore banned** — not as a style preference but because it names a counterpart
  that is illegal by construction, and because a suffix chain is what let two conventions coexist
  invisibly. It is removed from `MIGRATION_SUFFIXES` the moment the renames land.
* Every file keeps the **REUSE SPDX header** and the four linted keys `MI:`, `I:`,
  `COUNSEL-GATED:`, `RATIONALE:`.
* Rendered files additionally carry `-- @rendered-by  trappoint render` and **are never hand-edited**
  — a change to a rendered file is a change to its template followed by a re-render of **both**
  bindings (MAINLINE and `refvertical`).

`.up.sql` is a `trappoint migrate lint` **failure** today (rule C, `up-sql-suffix`). That rule was
deliberately red on this tree until the renames landed: a guard that was *observed* red is a guard
that asserts something, and there is no exemption list, no warning level and no environment
variable that downgrades it.

## MR-6 lock 1 — `migrations.allocation.toml` is the authority for numbers

**`verticals/mainline/db/migrations.allocation.toml` is the authority for migration numbers, and
it is enforced by `trappoint migrate lint`.** The band tables in the prose — in the reconciliation
ruling, in this plan, in any plan — are its *rendering*. Where prose and that file disagree, the
file is what lint enforces and the file is therefore what is true.

Lint resolves every discovered file against it and refuses three things:

* **Rule A · `filename-convention`** — the filename must match `^\d{4}[a-z]?_[a-z0-9_]+\.sql$`.
* **Rule B · `allocation-mode` / `allocation-unallocated`** — the file's `(NNNN, letter)` key must
  fall in a band, and the band's `mode` must agree with the file: a file carrying
  `-- @rendered-by  trappoint render` in an `authored` band is a refusal, and so is a file without
  that banner in a `rendered` band. **This is the rule that compares a file against a declaration
  rather than comparing two declarations with each other, which is the thing the collision check
  could not do.**
* **Rule C · `up-sql-suffix`** — `.up.sql` is a failure.

Two further consequences of the authority sitting in one file:

* **`0200` and above is UNALLOCATED and no file may use it, in either mode.** A number space with
  no owner is exactly what produced two conventions; a range that lint refuses is safer than a
  range someone can assume into.
* **Adding or moving a band is not an edit to that file alone.** A new band is carved out of an
  existing one, both sides are restated, and the result must remain exhaustive and disjoint over
  the whole key space — `packages/trappoint-migrate/tests/test_allocation.py` refuses an overlap
  and refuses a gap. A worker who needs a number that is not theirs asks the band's owner; a worker
  who has run out of numbers suffixes their own last number (MR-5's band overflow).

`verticals/mainline/db/migrations.lock.json` is **generated** by walking
`trappoint_migrate.discovery.discover()` over the tree and resolving each file against the
allocation. It is a manifest, not a declaration: a lock file that is hand-written is a second
source of truth, which is the class of failure this ruling exists to end.

<!-- ──────────────────────────── END OF THE COMMON BLOCK ──────────────────────────── -->

## What this changes in THIS plan — recall

**Almost nothing, and that is the finding.** Recall declared its numbers as bands *and* wrote
files that matched them, in the `.sql` convention, one statement per file — so the reconciliation
confirms this domain's §3 reservation rather than revoking it. **`0040`–`0046`, `0080`–`0089`,
`0110`–`0114` and `0136`–`0139` are confirmed and unchanged**, and `migrations.allocation.toml`
grants them to recall exclusively (`0040`–`0046z`, `0080`–`0089z`, `0110`–`0114z`,
`0136`–`0139z`). Three small corrections to §3's wording follow from that:

* The function band is **`0110`–`0114`**, not `0112`–`0114`. `0110` is `fn_candidate_project` —
  see the fourth split below.
* The table band is **`0080`–`0089`**, so "the remaining `mainline_meas` tables renumber to
  `0089+`" reads `0089`, `0089a`…`0089z` and stops there. `0090` is `datamodel/dm-periphery`'s.
* `0086`'s counsel gate (DM-17, `silence_ledger` in the unprivileged `mainline_meas` zone) is
  unchanged, and both halves of the `0086` split carry the same `COUNSEL-GATED: yes (G0)` header.

**Four files were split, for the one-statement-per-file rule and for nothing else.** Each carried
two top-level statements, which `statement_count()` reports and which the runner cannot apply
atomically — CockroachDB DDL is not transactional across statements, so a failure inside a
two-statement file leaves a half-applied migration and a `dirty` marker nobody can diagnose. **No
SQL body changed. The letter suffix is D7's multi-statement slot doing exactly the job it was
defined for.**

| Before | After |
|---|---|
| `0086_thymogate_certificate.sql` (`CREATE TABLE` + `ALTER TABLE`) | `0086_thymogate_certificate.sql` + `0086a_recall_policy_thymogate_fk.sql` |
| `0114_fn_cue_prefix_project.sql` (two `CREATE FUNCTION`) | `0114_fn_cue_prefix_project.sql` + `0114a_fn_cue_coarse_project.sql` |
| `0138_trg_cue_prefix_project.sql` (two `CREATE TRIGGER`) | `0138_trg_cue_prefix_project.sql` (embedding) + `0138a_trg_cue_prefix_project_coarse.sql` |
| `0139_trg_candidate_project.sql` (`CREATE FUNCTION` + `CREATE TRIGGER`) | **`0110_fn_candidate_project.sql`** + `0139_trg_candidate_project.sql` (trigger only) |

The fourth is the one worth reading twice: a `CREATE FUNCTION` sitting in a file numbered in the
*trigger* band inverts §18's stratification — the function would have been created after triggers
that could already reference it. Moving it to `0110` puts it back in the function band, ahead of
everything that reads it, and leaves `0139` as the trigger it is named for.

**Nothing else in this domain moves.** `0112`, `0113`, `0136` and `0137` are on disk, correct, and
were the reason MR-7 revoked `datamodel.md`'s `0130`–`0199` remap and MR-8 moved
`kernel/merge-gate-and-core` off `0111`–`0115`/`0135`–`0136`: four live collisions, and this
domain got the numbers because it had already written the files. Header `requires:` lines that
cite the old foundation numbers are corrected to the rendered ones (`0001a` business schema,
`0002` meas, `0003` audit, `0004` qa, `0005` ops); those are comments and nothing executes them.
D12's time-wall predicates and D14's THYMOGATE placement are untouched.

---

*Migration reconciliation, 2026-08-08. One convention, one authoring mode per number, one owner per band, and a lint that fails before a human has to notice. The collision check reported zero because it compared strings; the replacement compares a file against a declaration.*
