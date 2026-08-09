# AGENT FLEET & MCP — domain implementation plan

**Lead:** Agent fleet and the CockroachDB tool surface. **Date:** 2026-08-05.
**Authority:** `ARCHITECTURE.md` §8 (planes, determinism boundary, fleet, ingestion), §9 (all four CockroachDB capabilities), §10.2–10.3 (Bedrock, endpoints, identity), §11.2/§11.5 (roles, A-RULE), §12 (two telemetry classes), §16 (MI13/MI14/MI25), §17 (the MCP audit surface), §19 (`GT-*`) · `BUILD_PLAN.md` K4/K6, §5.2 beat 5, §11 (OSS track) · `research/06-build/agent-architecture.md`, `research/05-architecture/crdb-deep-verify.md`, `research/06-build/oss-packaging.md`.
**Licence boundary:** `packages/mainline-agentkit`, `packages/mainline-mcp`, `packages/mainline-indextruth`, `packages/mainline-boundary`, `packages/trappoint-mcp`, `skills/` → Apache-2.0. `verticals/mainline/**` → FSL-1.1-ALv2.

---

## 0. The domain in one sentence

This domain owns **everything that reasons and everything a stranger can point a tool at** — and its deliverable is the pair of sentences *"no component that touches an untrusted document holds a tool, a write credential, or a path to the gate"* and *"a judge can interrogate the ledger over CockroachDB's own endpoint, with none of our code in the path."*

Two structural properties carry the whole domain, and both are enforced rather than asserted:

- **The components that read hostile text have no capability to act on it.** Not a policy — a call shape. `quarantined_call()` has no `tools` parameter, and CI fails if the ingest packages ever construct one.
- **The two components that hold a tool loop are the two that cannot write a field the gate reads.** The Steward (headless Claude Code over Managed MCP) and the auditor persona (the judge's own agent, not our code) both live in the Control plane.

---

## 1. Decisions made here (each with one line of justification)

| # | Decision | Justification |
|---|---|---|
| **A1** | **No agent framework in the Cognition plane.** Every MAINLINE model call is a *single-shot, zero-tool, JSON-Schema-constrained* Bedrock call issued by `mainline-agentkit` (~600 lines). Strands and LangGraph evaluated and rejected. | A framework whose value is the tool loop is worth nothing to a fleet whose defining security property is that the components touching untrusted text hold **no tools**; LangGraph's checkpointer would be *a second, weaker record of a legally significant process* — the exact objection that already rejected Step Functions (§10.2); and `strands-agents 1.50.2` pins `mcp<2.0.0,>=1.23.0`, which in a one-lockfile uv workspace forces our own MCP server off protocol revision 2.x. **Reconsider trigger:** Strands supports `mcp>=2` *and* a genuine multi-tool loop appears in Cognition. |
| **A2** | **The only tool loops are (a) the Steward — headless Claude Code + `.mcp.json` + CockroachDB Agent Skills, and (b) the auditor's own agent.** Neither is Python we ship on the merge path. | §8.3 already specifies the Steward this way and §10.3 already says the auditor path "contains none of our code". Building a Python tool loop would add a third, weaker copy of a loop we do not need. |
| **A3** | **Transport = `bedrock-runtime` `InvokeModel` (boto3) with the Anthropic native body (`anthropic_version: "bedrock-2023-05-31"`) and an `au.*` inference-profile ARN as `modelId`.** Not the `AnthropicBedrockMantle` client, not `Converse`. | The residency control is a **VPC-endpoint policy enumerating `au.*` inference-profile ARNs on the `bedrock-runtime` endpoint** (§10.1). The Mantle path terminates on `bedrock-mantle.{region}.api.aws` — a different endpoint whose policy surface is unverified — and `Converse` cannot express `output_config.format`. `GT-AG-01` verifies the native body accepts `output_config` on a profile ARN; the cassette provider covers CI either way. |
| **A4** | **One model generation across the whole fleet: `claude-opus-5` via its `au.*` profile, differentiated by `output_config.effort` (`low` triage/extraction · `high` adjudication/NLI · `xhigh` listwise rerank).** Haiku triage is **rejected** as the default. | Three reasons, all measured facts: Opus-5's minimum cacheable prefix is **512 tokens** vs Haiku 4.5's **4096**, so our shared rubric prefix actually caches instead of silently costing full price; one model id ⇒ one profile ARN in the endpoint policy ⇒ one 403 path instead of two (open question 8); and `low` effort on Opus 5 is documented as unusually strong. Falling back to Haiku is an ADR with a measured cost number, not a default. |
| **A5** | **Thinking is `{"type": "adaptive"}` explicitly on every call — never omitted, never `disabled`.** `effort` carries the cost lever. | On Opus 5 thinking is **on by default** and `disabled` is a 400 above `high` effort; `disabled` also causes two silent failures — a tool call written into visible text (the call never runs, no error) and `<thinking>` tag leakage. Writing the field explicitly makes the request self-documenting across model generations; `max_tokens` caps thinking **plus** text, so every profile carries a sized floor and `stop_reason == "max_tokens"` is a **hard failure**, never a truncation we absorb. |
| **A6** | **No sampling parameters, anywhere.** A repo-wide grep bans `temperature`, `top_p`, `top_k` from every request builder. | They return 400 on this generation, and the honest claim was never reproducibility (§8.2) — it is *replayability* + *arithmetic reproducibility*. A parameter that cannot exist cannot be blamed for drift. |
| **A7** | **JSON Schema for `output_config.format` is machine-derived from the Pydantic model by `bedrock_schema()`, which strips the documented-unsupported keywords** (`minLength`/`maxLength`, `minimum`/`maximum`/`multipleOf`, array-size constraints, recursion) **and forces `additionalProperties: false`.** The stripped invariants are re-imposed as **client-side validators**. | Structured outputs silently ignore or reject those keywords; a "≤60-token cue" expressed as `maxLength` would be an unenforced promise. A golden-vector test asserts the stripped keyword set equals the documented set exactly, so a schema-feature change breaks a test rather than a control. |
| **A8** | **Refusal is silence, and silence is a row.** Check `stop_reason` **before** touching `content`; branch on `stop_reason` only (`stop_details` may be `null`); write `silence_ledger(outcome='silenced', reason='model_refusal')`; fall back **client-side** to the deterministic channel. Server-side `fallbacks` is unavailable on Bedrock. | Our corpus is cyanide leaching, H₂S and confined-space chemistry — false-positive refusals are expected. *A precursor the model declined to summarise must still block the merge.* |
| **A9** | **Prompt caching is explicit and asserted.** Automatic caching does not exist on Bedrock: every profile places one `cache_control: {"type":"ephemeral"}` breakpoint on the last system block, over a byte-frozen prefix; a cassette-replay test asserts `cache_read_input_tokens > 0` on call #2. **Fan-out never starts cold:** send one call, await the first streamed token, then fan out the rest. | A cache entry is readable only once the first response *begins streaming* — N parallel identical-prefix calls all pay full price. An un-asserted cache is usually a broken cache. |
| **A10** | **`explain_query` over Managed MCP asserts ONE arm per call**, looped with a bound; the full ~12-arm `UNION ALL` plan is asserted over pgwire. | The MCP response cap is **10 KiB** and `explain_query` accepts SELECT/INSERT/CREATE TABLE only. A 12-arm plan would truncate — and *a silently truncated proof of index use is exactly the defect this product exists to refuse.* Per-arm byte size is recorded so the headroom is a number, not a hope. |
| **A11** | **The MCP audit surface has a byte budget with headroom, and negative assertions are first-class.** Every view must return ≤25 rows **and ≤8 KiB measured** (80 % of the cap); `mainline_qa`, `crdb_internal`, `pg_catalog`, `information_schema` must be **unreachable**; `insert_rows` must succeed **only** on `mainline_meas.external_attestation` and fail everywhere else. | S14 plus §17: the size limit is a *functional requirement*, and a limit tested at 100 % breaches in front of a judge the first time the corpus grows. A negative assertion beside every positive one is what turns a claim into a test. |
| **A12** | **The audit-view *contract* is mine; the audit-view *DDL* is the data-model lead's.** `spec/mcp/audit-surface.contract.yaml` names each view, its columns, its truncation flag and its budget; `dm-views-rls` implements it in migrations `0200–0279`. | Two leads cannot own one migration band. The contract is what the build consumes; the recall lead's note that `v_recall_conservation` / `v_silence_summary` are "the MCP lead's to write" resolves in this direction, and this line is the resolution. |
| **A13** | **Prompt edits are commits, not deploys.** `agent_identity := sha256(agent_name ‖ sql_role ‖ iam_role_arn ‖ prompt_version ‖ model_id ‖ inference_profile_arn ‖ schema_version)`; every prompt asset is content-addressed, registered, and a change to one opens a `change_request`. | A quiet prompt edit that suppressed a class of precursor must itself be a gated, attributable change. This is the same recursion DIRECTRIX applies to the gate's parameters, applied to the fleet's prompts, and it costs one table. |
| **A14** | **The determinism boundary is asserted four independent ways, and none of them is a comment.** AST/SBOM scan (no model SDK, no `boto3.client("bedrock*")`, no `anthropic` import in kernel or gate-service packages) · IAM permissions-boundary simulation over the plan · VPC-endpoint absence + SG-egress assertion over the plan · a fleet capability-matrix test driven by `spec/agents/fleet.yaml`. | *A regulator must be able to read the merge gate in ten minutes and see no model in it* — and E2 is the one that convinces a reviewer because it does not depend on our code being correct. AWS credentials are not yet valid, so E1/E2 run against a committed OpenTofu **plan JSON** and become live checks in `cloud-verify.yml` the day credentials work (PL-3). |
| **A15** | **Our own MCP server (`trappoint-mcp`) never signs.** `draft_disposition` returns an *unsigned* draft plus a signing URL; `disposition` is written only by a human-authenticated pgwire path. Pin `mcp>=2.0,<3` (2.0.0, 2026-07-28), surface capped at four tools. | *"An agent signed away a fatality-linked precursor"* becomes structurally impossible to produce in discovery, and it costs one tool boundary. A1 is what makes the 2.x pin available at all. |
| **A16** | **Upstream contribution targets an EMPTY domain: `verifying-a-restore-by-merkle-root` → `cockroachdb-resilience-and-disaster-recovery`.** Verified 2026-08-05: that directory is still `.gitkeep`-only (repo: 18 stars, last push 2026-07-22, four empty domains). We publish `designing-diachronic-gates` under our own brand; `designing-vector-recall-prefixes` belongs to the recall lead. | Being the *first* skill in an empty domain is a materially better claim than the thirteenth in the most crowded one, it removes a scheduled job with no software behind it, and it avoids filing over PR #17. **Claim the filing, never the merge** — CI-grepped. |

---

## 2. Sequencing, and where the red tests go

```
W1 spec/agents + spec/mcp + the RED CI job            ← nothing else may start green
      │
      ├── W2 agentkit  ──┬── W4 injection defence (needs the zero-tool call shape)
      │                  └── W10 boundary assertions
      ├── W3 provenance ledger  ── W7 steward (needs agent_identity + ops_attestation)
      ├── W5 MCP client + auditor ──┬── W6 explain/index-truth
      │                             └── W7 steward (needs the MCP client)
      ├── W8 skills (independent; ships even if the cloud slips)
      └── W9 trappoint-mcp (independent; the OSS artefact)
```

**PL-2 is structural.** `W1` ships `tests/agents/test_red_gate.py` with four assertions that **must be red on first commit**:

1. every agent in `fleet.yaml` has an implemented call profile or an explicit `no_model: true`;
2. no package reachable from the kernel imports a model SDK;
3. every `mainline_audit` view named in the contract returns ≤25 rows and ≤8 KiB **measured over the live MCP endpoint**;
4. `mainline_qa` is **unreachable** from the MCP identity.

They go green one worker at a time. A fleet-conformance suite that has never been red asserts nothing about a fleet whose deliverable is a refusal.

**Everything runs with no AWS account.** The cassette provider is the default in CI (`MAINLINE_AGENT_PROVIDER=cassette`), keyed `sha256(profile_id ‖ prompt_version ‖ jcs(input))`, committed. The live Bedrock path exists, is off by default, and is never exercised in CI — the CI job carries a network egress deny-list so an accidental live call fails loudly rather than silently costing money and non-determinism.

---

## 3. Interfaces this domain publishes

| Artefact | Consumer | Contract |
|---|---|---|
| `spec/agents/fleet.yaml` | W2, W4, W7, W10, submission | agent ⇄ tier ⇄ sql_role ⇄ tools ⇄ may_write_gate_field ⇄ call_profiles |
| `spec/agents/model-call.contract.md` | every model caller in the repo, incl. `recall-providers` | request shape, refusal handling, cache placement, ledger row |
| `spec/mcp/audit-surface.contract.yaml` | `dm-views-rls` (implements), W5/W6 (asserts) | view ⇄ columns ⇄ truncation flag ⇄ row cap ⇄ byte budget |
| `spec/mcp/negative-assertions.yaml` | W5 | schema/tool pairs that MUST fail, with expected error class |
| `mainline_agentkit.call.quarantined_call()` | ingest, fixity, cherry-pick, disposition-assistant callers | zero-tool, schema-constrained, ledgered; **has no `tools` parameter** |
| `mainline_agentkit.schema.bedrock_schema(Model)` | every structured-output caller | Pydantic → Bedrock-legal JSON Schema + the client-side validator set |
| `mainline_provenance.emit(AgentAction)` | every agent | writes `agent_action_provenance`; `agent_identity` resolved once at start-up |
| `mainline_mcp.Client` + `AuditorPersona` | W6, W7, `VERIFY.md`, the demo | four verbs, budget-measured, negative-asserted |
| `packages/trappoint-mcp` (`server.json`) | anyone; the MCP registry | four tools, insert-only, **never signs** |
| `skills/designing-diachronic-gates` | skills.sh, plugin marketplace | `assert_gate_refuses.py` spins a throwaway node and fails unless the DB raises the expected SQLSTATE |

**Migration band reserved: `0300–0319`.** Three new objects only — `mainline_meas.agent_identity`, `mainline_meas.prompt_asset`, `mainline_meas.agent_action_provenance` (FK to the data-model lead's `agent_action`) — plus `mainline_audit.v_agent_provenance`. *Note for the warden:* `dm-views-rls` claims `0200–0279` and the algorithms domain claims `0200–0219`; that overlap is theirs to resolve, and `0300+` avoids both.

---

## 4. What this domain does **not** claim

> The Managed MCP identity is assumed **admin-equivalent** and RLS is assumed **not** to apply. `mainline_audit` views are therefore designed to be safe if read in full, `mainline_qa` never receives an account, and **we never market MCP as site-scoped.** `security_invoker` (v26.2) is the upside lever if `GT-10` says the identity is a non-admin role.

> An LLM ops report is evidence that **a review occurred**, not evidence of a condition. Every Steward finding carries the SQL it ran and the sha256 of the result rows so a reader can re-run it.

> Prompt-injection defence does not fix a **plausible-but-false narrative in an otherwise clean PDF**. Content authenticity is out of scope; provenance is in scope.

All three sentences are CI-grepped strings in the README, `VERIFY.md` and the deck.

---

## 5. Worker roster

| # | id | One-line purpose |
|---|---|---|
| 1 | `agent-contracts-red` | The fleet register, the model-call contract, the MCP audit-surface contract with its negative assertions — and the four assertions that must fail on day one. |
| 2 | `agentkit-core` | The zero-tool constrained-call runtime: `au.*` transport, Bedrock-legal schemas, explicit caching, refusal-as-silence, one-retry-then-dead-letter, cassettes. |
| 3 | `agent-provenance` | `agent_identity`, content-addressed prompt assets, the per-action provenance row, and the rule that a prompt edit opens a change request. |
| 4 | `injection-defence` | The six-layer posture as executable controls plus a hostile-document corpus that proves a poisoned PDF cannot reach a tool, a credential, or a gate field. |
| 5 | `mcp-client-auditor` | The Managed-MCP client, the auditor persona's question→view catalogue, the response-budget prober, and the negative reachability suite. |
| 6 | `explain-index-truth` | The plan-fragment parser and the three-layer proof that the vector index was used — asserted arm-by-arm over CockroachDB's own public endpoint. |
| 7 | `steward-ops` | Headless Claude Code over the Agent Skills repo on a schedule, with every run hashed into the ledger as an ops attestation and the one permitted MCP write. |
| 8 | `skills-published` | The branded diachronic-gate skill with its refusal-proving script, and the upstream filing into an empty CockroachDB skills domain. |
| 9 | `trappoint-mcp-server` | Our own MCP server on the official SDK 2.x — four tools, insert-only, and the boundary that means it can never sign. |
| 10 | `determinism-boundary` | The four independent proofs that no model can reach the merge gate, plus the fleet capability matrix and the domain's CI greps. |

---

## 6. Risks I am accepting

| # | Risk | Position |
|---|---|---|
| **AR-1** | **`GT-AG-01` fails: the native `InvokeModel` body rejects `output_config` on an `au.*` profile ARN.** | Pre-committed fallback: constrained generation moves to `strict: true` **tool-use** with a forced `tool_choice` (a tool the model must call, whose input schema is the extraction schema) — same JSON Schema, same validator, one extra shape. This is a *format* fallback, not a capability fallback, and it is written before it is needed. It does **not** re-introduce a tool loop: `tool_choice` is forced and the loop terminates at one turn. |
| **AR-2** | **`GT-11` returns no `au.*` profile for the current Claude generation.** | Ship the previous generation and say so in the README — but note A4's cache minimum is generation-dependent (512 vs 1024 vs 2048 vs 4096 tokens), so the fallback also re-tunes the shared prefix length. The profile ARN is **resolved at runtime and pinned into the ledger**, never hard-coded, so this is a data change. |
| **AR-3** | **`GT-17` forbids publishing an MCP service-account key to anonymous judges.** | Beat 5 degrades to a *recorded* MCP session plus our own read-only aggregate endpoints, and `VERIFY.md` states exactly why. We never publish a key on the demo cluster regardless — the write surface is insert-only but it is real. |
| **AR-4** | **The upstream PR is ignored.** Two external skill PRs have sat untouched for weeks (the repo is *not* dead — PR #18 merged 2026-07-22). | Nothing downstream depends on it. We claim the filing, never the merge, and the submission says "**these two PRs**", never "the repo is stalled". |
| **AR-5** | **`insert_rows` executing server-side triggers is unverified (`GT-09`).** | Safe under either answer: the one MCP-writable table (`external_attestation`) is trigger-free by construction, and a test asserts it stays that way. |
| **AR-6** | **An audit view grows past the byte budget as the corpus grows.** | The prober measures actual bytes nightly and fails at 8 KiB, not 10 — the alarm fires with 20 % of headroom left, and the failure lands in CI rather than in front of a judge. Accepted residual: a single pathological row (a very long site code) could still spike one view; the prober records the worst observed row so the cause is nameable. |
| **AR-7** | **Cassette drift.** Everything green in CI is green against recorded model output; live behaviour can diverge silently. | Accepted and named: the nightly `cloud-verify` lane replays a fixed sample against the live path and diffs *schema conformance and refusal class*, never text. We claim replayability and arithmetic reproducibility, never reproducibility of model output. |
| **AR-8** | **We cannot prove a Steward finding is true — only that a review ran.** | Stated as a CI-grepped sentence rather than mitigated. The per-finding SQL + result-row hash is what makes the weaker claim checkable. |
| **AR-9** | **The injection corpus is ours, so it is not adversarial in the way a real attacker is.** | The corpus is published with the repo so a stranger can add to it, and every blocked extraction writes `document_intake_finding` — *the injection is evidence*. We do not claim coverage; we claim that a hostile document reaches a component with no capability to act on it. |

---

*Agent fleet and MCP lead, 2026-08-05. Ten workers, sixteen decisions, nine accepted risks. The domain is done when a stranger with no credential of ours can point their own agent at the cluster, ask what we declined to surface, and get an answer that is small enough to fit in 10 KiB and honest enough to be worth reading.*

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

## F7 — ccloud CLI: MEASURED, and the headless-auth assumption is WRONG

Verified 2026-08-10 against the live cluster. **This corrects a design assumption made in the agents-mcp lead plan and in the `am-steward-ccloud` brief.**

**What is true:**
- `ccloud` **0.6.12** is the current published Windows build (`https://binaries.cockroachdb.com/ccloud/ccloud_windows-amd64_0.6.12.zip`). Probes for 0.7.0 / 0.8.0 / 0.9.0 / 1.0.0 all return **404** — 0.6.12 is it. Its embedded API stamp reads `CCAPI 2023-04-10`.
- `-o json` is present as a **global flag on every command** — that part of the "agent-ready" claim holds.

**What is FALSE (and was assumed):**
- **`ccloud` has NO non-interactive service-account authentication.** `ccloud auth` offers only `login` / `logout` / `whoami`; `login` is browser-based. Setting `CC_API_KEY` in the environment is ignored — every API-touching command returns `Error: not logged in. Use 'ccloud auth login' to login`. There is no credentials file to pre-seed (`~/.ccloud` does not exist until an interactive login creates it).
- Therefore **an agent cannot drive `ccloud` headlessly from a cold start**, which is what `am-steward-ccloud` was briefed to build.

**The capability IS real — through the Cloud REST API, not the binary.** The same service-account key works immediately as an HTTP Bearer token:

```
curl -H "Authorization: Bearer $CC_API_KEY" https://cockroachlabs.cloud/api/v1/clusters
```
Measured, live: returns `mainline-dev`, `v26.2.5`, plan `BASIC`, provider `AWS`, state `CREATED`, routing id `mainline-dev-31219`, `request_unit_limit: 100000000`. `/sql-users` likewise returns `mainline-sql`. So headless provisioning, inspection, SQL-user management and audit retrieval are all available to an agent — over the API.

**RULING:** the Steward keeps `ccloud` for anything a human runs and for the recorded, replayable transcript (its `-o json` output is genuine and worth showing), but **its headless control-plane path is the Cloud REST API with the service-account bearer token**. Build both, and say exactly which is which.

**Honesty requirement:** do NOT claim "the agent provisions the cluster by driving the ccloud CLI headlessly" — that is not achievable with 0.6.12. The truthful claim is: *"the ccloud CLI is used, with `-o json` parsed rather than screen-scraped, and the same service-account credential drives the Cloud API for headless paths where the CLI requires a browser."* That is still a genuine, demonstrable use of the tool — and being precise about it is worth more to a judge than an overclaim they can falsify in thirty seconds.
