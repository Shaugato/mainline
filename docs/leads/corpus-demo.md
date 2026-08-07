# Domain plan — CORPUS & DEMO

**Lead:** Corpus & Demo (the synthetic world and the three-minute film).
**Authorities implemented, not re-derived:** `ARCHITECTURE.md` §2.2 (S3, S4, S5, S10, S16, S21, S26), §5.2–5.9 (DDL the corpus must satisfy), §11.7 (must-not-claim), §17 (MCP audit views), §19 (`GT-*`), §20; `BUILD_PLAN.md` §5.1–5.5 (⟦H⟧ depth, beat→milestone tagging, schedule, silent disqualifiers); `research/06-build/demo-engineering.md` (stages 1–5, injector table, spine, toolchain, script); `research/06-build/incident-ingestion.md` §4, §6, §9 (severity axes, basis-graded force, evaluation methods).

---

## 1. The thesis of this domain in three sentences

The corpus is not demo dressing. It is simultaneously **(a)** the film's factual substrate, **(b)** gold set **GS0** — the answer key against which the recall harness's precision is *measurable rather than asserted*, and **(c)** the fixture bundle that lets a judge reproduce the merge refusal on a laptop in four minutes with no cloud account. Every design choice below is decided by which of those three it would break.

The corresponding failure mode is precise: an LLM asked for "a realistic safety corpus" returns fluent prose with no causal structure, blame walks come out one hop deep, precision cannot be computed, and the demo becomes theatre. **We author causality and render text second**, so the answer key exists by construction.

---

## 2. Decisions made here, one line of justification each

| # | Decision | Why |
|---|---|---|
| **D1** | **Beat 4 is M8 DEFEATER LEASE**, filmed SQLSTATE **`P0001`**, message `MAINLINE: precursor arrived after issue`. `23503` is never filmed. | S3 + S4: M14 SHEPARD has no tables; the `RAISE` fires before the epoch-pin `UPDATE`, so `23503` cannot occur and filming it would be the exact overclaim we punish. |
| **D2** | **Three renderer tiers** — `authored` (hand-written fixtures, everything on camera), `bedrock` (`au.anthropic.claude-sonnet-4-5-20250929-v1:0`, strict tool-use JSON, T=0, cached), `template` (deterministic offline). **`--offline` is the default; `--allow-live` is required to reach Bedrock.** | AWS credentials are not valid on the founder's machine and PL-3 forbids an unproven capability on a dated path. The film's prose therefore has **zero live-model dependency**, and the corpus still ships. |
| **D3** | **Offline fixture embeddings = `model2vec` `potion-base-8M` (MIT, CPU, static) + a fixed orthonormal 256→1024 lift**, cosine-preserving to <1e-5. Titan v2 replaces them behind an `index_gen` bump if AWS lands before D-5. | The vocabulary-drift injector's entire claim is *lexical fails, semantic succeeds*. A hashed-lexical surrogate would falsify the corpus's own claim; a real static encoder makes the claim **measured** with no AWS. A random orthonormal lift preserves inner products exactly, so the production vector width is honoured without distorting geometry. |
| **D4** | **.docx output is byte-reproducible**: fixed member timestamps `(1980,1,1,0,0,0)`, sorted member order, pinned `docProps/core.xml` `dcterms:created/modified`, no per-run ids. | `python-docx`'s `_ZipPkgWriter` stamps wall-clock into every zip member; without the fix `MANIFEST.sha256` is unreproducible and the judge-facing reproducibility claim is false. |
| **D5** | **Per-stream RNG.** `Random(int.from_bytes(sha256(master_seed‖stream_name)[:8]))`, one stream per generator; never one global stream. | Otherwise adding a single generator shifts every downstream draw, the render cache misses wholesale, and "regeneration is a no-op unless a prompt changes" stops being true. |
| **D6** | **The 2016 retypeset is a genuinely different second template** — different numbering scheme, different style set, different clause ordering — not a string substitution. | Clause reflow must be *real*; identity survival across reflow is the K3 exit criterion and beat 1's payload. |
| **D7** | **The answer key is authored by the generator that created the causal fact**, never inferred afterwards; each true edge independently draws whether it leaves a documentary trace (`p_doc≈0.55`). | Gives held-out asserted-link evaluation real masked positives and gives capture–recapture (channel A = citation resolver, channel B = semantic) something to estimate. |
| **D8** | **The loader never writes a projected column.** A `PROJECTED-COLUMNS.yaml` denylist plus a test that parses every emitted `INSERT` and fails on a denied column name. | P2. A corpus loader that writes `open_blocking` or `sev_max` directly would launder the flagship claim one hop upstream — the same defect class as S1. |
| **D9** | **`corpus.lock.json` is generated, never hand-written**, and is the single source of truth for preflight row counts, honesty-card numbers and the renderer census. | One number, one place. The honesty card is *generated from* the lock, so it cannot drift from the corpus and cannot lie about how much prose a model wrote. |
| **D10** | **Contract tests assert invariants and ratios, not hard-coded totals** (`events ≥ 1000`, `sev5 ≥ 4`, `blame_edges/clause_versions ∈ [0.15, 0.30]`, …). | Hard-coded counts make every corpus tweak a red CI run, which trains the founder to ignore red. |
| **D11** | Fixture embeddings are **float16 zstd `.npy` shards ≤ 10 MB total**, cast to float32 at load; scoped to the ⟦H⟧ slice + the recall harness's needs. | 11 240 × 1024 × f32 = 46 MB is not a git artefact. fp16 round-trip is deterministic, and the dtype is recorded in the lock. |
| **D12** | **Kestrel Resources Pty Ltd**, sites Marrindal / Cape Verity / Yandarra Downs / Tolgarra, cleared against **ASIC company search, ABN Lookup, IP Australia trade marks** with dated evidence and **three pre-cleared fallback names**. | Satisfies the no-third-party-trademark rule affirmatively rather than by hope, and the dossier is the artefact that proves it. |
| **D13** | **VHS prompt is `mainline_demo=>`** and a tape linter forbids `/` anywhere inside a `Wait` regex. | vhs#592: a forward slash cannot be escaped inside `Wait`; discovering that on capture day costs the shoot. |
| **D14** | **Playwright `page.clock.setFixedTime()` only**, never `install()`, pinned to `2026-08-04T09:14:00+10:00`. | On-screen timestamps must be byte-identical across three takes; `install()` has ordering hazards and buys nothing here. |
| **D15** | **The film has no live-Bedrock dependency at capture time.** Embeddings are pre-seeded; every on-camera round trip is CockroachDB or the managed MCP. | The one external dependency we cannot currently verify is removed from the critical path of the one artefact that must exist. |
| **D16** | Four sites in the corpus; **one site on camera**. | Fleet siblings need ≥3 sites to be real; ⟦H⟧ breadth cuts cost nothing on camera. |

**Genuine choices the documents left open, made here:** D2 (tiering the renderer), D3 (the orthonormal lift), D5 (per-stream RNG), D7 (documentary-trace sampling), D10 (invariant-shaped assertions), D11 (fp16 shards). Everything else implements a decision already taken.

---

## 3. Sequencing, and where red-before-green lives

`W1` is the red suite and nothing else. **It must be committed and failing before any generator code exists** — for a domain whose deliverable is an answer key and a refusal, a suite that has never been red asserts nothing (PL-2). The suite fails with explicit `NotImplementedError` / missing-artefact assertions, never with `ImportError`, so "red" means "unbuilt", not "broken".

```
W1 corpus-contract  ─┬─► W2 skeleton ─┬─► W3 blame-key + injectors ──┐
   (RED SUITE)       │                └─► W4 spine + operator clearance ─┐
                     └─► W5 render/cache ─┬─► W6 docx (+ retypeset) ─────┤
                                          └─► W7 embed lift ─────────────┤
                                                                         ▼
                                                          W8 freeze + loader + CI
                                                                         │
                     W9 script + honesty + VERIFY ◄──── W3, W4 ──────────┤
                                                                         ▼
                                                        W10 preflight + tapes + capture
```

Milestone alignment (`BUILD_PLAN` §5.3): W1–W2 on **D-14**, W3–W5 by **D-12/D-11**, W6–W8 by **D-10** (corpus **frozen** at `G2`), W9 by **D-7** (so the VO can be cut 20 % on D-4), W10 by **D-7** (`just demo:preflight` written before the scope-cut ladder triggers).

**The five red assertions that matter most**, all in W1:

1. `test_two_runs_identical` — the whole skeleton, twice, same sha256 manifest.
2. `test_spine_facts` — the eight dated spine facts exist with the exact strings, `clause_uuid` constant across 2011→2013→2016→2019→2026.
3. `test_docx_byte_identical` — same input, two runs, identical bytes (and identical across the ubuntu/windows CI matrix).
4. `test_camera_strings_agree` — the 2013 commit message string is **byte-identical** in the authored fixture, `VO.md`, `SHOT-LIST.yaml` and the generated honesty card. One string, four files, one test.
5. `test_no_projected_column_written` — every `INSERT` the loader emits, parsed, checked against `PROJECTED-COLUMNS.yaml`.

---

## 4. Interfaces this domain publishes and consumes

**Publishes**

| Artefact | Consumer | Shape |
|---|---|---|
| `verticals/mainline/fixtures/corpus/answer-key/gs0.jsonl` + `gs0.schema.json` | Recall lead (GS0), evaluation harness | one row per (event, clause) with `label`, `basis`, `p_doc_trace`, `generative_reason`, `decoy_of`, `negative_control` |
| `verticals/mainline/fixtures/corpus/corpus.lock.json` | Preflight warden, honesty card, CI | generated; counts, sev histogram, renderer census, model ids, prompt versions, embed provenance |
| `verticals/mainline/demo/browser/SCREEN-CONTRACT.md` | Console lead | the `data-testid` list, fixed-clock tolerance, no-animation rule for the three recorded screens |
| `verticals/mainline/demo/REFUSAL-STRINGS.yaml` | Kernel lead (cross-check), tapes, VO | every on-camera constraint name, SQLSTATE and `RAISE` message, verbatim |
| `verticals/mainline/packages/mainline-corpus/PROJECTED-COLUMNS.yaml` | Datamodel lead (cross-check) | columns no writer outside a trigger may name |

**Consumes** — `verticals/mainline/db/migrations/*` (table list for the loader), `spec/errors.md` (refusal taxonomy; cross-checked when present, warn-then-fail), the `G1` ground-truth attestation JSON (honesty-card strings are generated from it; a fixture attestation ships so W9 is not blocked).

---

## 5. Worker roster

| # | id | Purpose in one line |
|---|---|---|
| 1 | `corpus-contract` | The corpus contract, its JSON Schemas, the CLI skeleton, and the entire **red** test suite, written before any generator. |
| 2 | `corpus-skeleton` | Stage 1: deterministic site/asset/energy graph, ICMM-anchored activity taxonomy, people, incident timeline, MOC stream, revision cadence — zero LLM, zero AWS, zero DB. |
| 3 | `corpus-blame-key` | Ground-truth blame edges + the eight realism injectors + `gs0.jsonl` with negative controls, decoys and capture–recapture channel labels. |
| 4 | `corpus-spine-authored` | The 22-year spine as hand-authored verbatim fixtures (everything on camera) plus the Kestrel Resources clearance dossier. |
| 5 | `corpus-render-cache` | Stage 2: three-tier renderer, strict-JSON Bedrock client on `au.*`, content-addressed committed cache, offline-by-default with a socket guard. |
| 6 | `corpus-docx` | Stage 3: byte-reproducible `.docx` via `docxtpl`, two template generations per family, the 2016 retypeset as a real second template. |
| 7 | `corpus-embed-lift` | Offline fixture embeddings via `model2vec` + cosine-preserving orthonormal lift, plus the measured lexical-vs-semantic drift margin published into the lock. |
| 8 | `corpus-freeze-load` | Stage 4: `corpus.lock.json`, `MANIFEST.sha256`, `corpusgen --verify` with zero Bedrock calls, the projection-safe DB loader, local Docker reproduction, `corpus.yml`. |
| 9 | `demo-script-honesty` | The locked shot list (+ the MWS fallback shot list), the VO, `DEMO-HONESTY.md`, the generated four-column card, the claim-hygiene grep, `VERIFY.md` with the MCP snippet. |
| 10 | `demo-harness` | The preflight warden, the four VHS tapes, the Playwright demo spec + screen contract, the evidence capture recorder, and the video CI gates. |

---

## 6. Risks accepted, and what we do instead of pretending

| Risk | Posture |
|---|---|
| **Bedrock never becomes reachable before D-1.** | Accepted and designed around: every camera-facing word is `authored`, the bulk is `template`, and the lock's renderer census makes the honesty card state the truth automatically. The corpus is complete without a single model call. |
| **`potion-base-8M`'s real dimension is not 256.** | The build asserts the encoder's actual dimension against the lift's expectation and **fails loudly**; the lift matrix is regenerated for whatever the true dimension is. No claim is made from a model card. |
| **Fixture embeddings are not Titan v2 on camera.** | Stated in the card, generated from the lock. The C-SPANN claim is about the *index and its `EXPLAIN` fragment*, which is unaffected by which encoder produced the vectors. |
| **The console is another lead's and may miss the screen contract.** | The contract is a committed file with a Playwright spec that fails against a static mock; the console lead sees a red test, not a conversation on capture day. |
| **The corpus's causal realism is authored, therefore friendly to our own linker.** | Mitigated by the decoy (60) and negative-control (≥200) sets, which are authored *adversarially* — same asset, same window, same vocabulary, different `hazard_energy` and different failed control. Stated in `DEMO-HONESTY.md`: a synthetic gold set bounds the linker from above, and the real-corpus sets (K8) are what settle it. |
| **`sev_max`/`open_blocking` drift between fixture and trigger-derived truth.** | The loader is forbidden from writing them (D8) and W8's integration test compares post-load projections against an independent re-derive. If they disagree the corpus is wrong, which is the correct place for that to surface. |
| **Capture day slips.** | From D-5 a submittable cut exists; `SHOT-LIST-MWS.yaml` (four beats, 2:38) is written on D-7, not improvised. The bypass beat is never cut for time. |

**Not claimed anywhere in this domain:** that the synthetic gold set measures real-world precision; that a disposition can be distinguished from a rubber stamp; that the film's prose was model-generated when it was authored; that commit dates are MVCC time travel (`gc.ttlseconds` is 4 h and the card says so).

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
