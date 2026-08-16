<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# FEATURE CENSUS — the plan

**Lead:** feature-census lead · **Date:** 2026-08-16 · **HEAD:** `5f57146` · **Deadline:** 2026-08-18 17:00 EDT

The deliverable is the **authority the film's close block and the Devpost submission are both written from**: every AWS service and every CockroachDB feature this project actually uses, each with a location, a sub-minute verification, and a state. Nothing in this plan authorises a deploy, a commit, a grant widening, or a claim that was not measured.

---

## 0. WHAT WAS MEASURED BEFORE THIS PLAN WAS WRITTEN

Every number below was produced today against the live cluster, the live origin, or the tree at `5f57146`. No worker should re-derive these; they should extend them.

### 0.1 The contest rules (fetched, quoted)

From <https://cockroachdb-ai.devpost.com/> — the four CockroachDB tools, **at least two** required:

1. CockroachDB Cloud Managed MCP Server
2. CockroachDB Distributed Vector Indexing
3. ccloud CLI (Agent-Ready)
4. CockroachDB Agent Skills Repo (Open Source)

AWS: submissions "must also use at least one AWS service".

Judging criteria, in the order printed:
**1. Agentic Memory Design · 2. Technological Implementation · 3. Real-World Impact · 4. Product Readiness · 5. Creativity & Originality.**

From <https://cockroachdb-ai.devpost.com/rules>, verbatim, and this is the fact that shapes the whole census:

> "if two or more Submissions are tied, the tied Submission with the highest score in the first applicable criterion listed above will be considered the higher scoring Submission."

> "The Project must be capable of being successfully installed and running consistently on the platform for which it is intended and must function as depicted in the video and/or expressed in the text description."

> "Judges are not required to test the Project and may choose to judge based solely on the text description, images, and video provided."

**Two consequences, and they pull in opposite directions.** The tie-break makes *Agentic Memory Design* the axis worth depth. The last sentence means a judge may never run anything — so the census must be readable and checkable **as prose**, not only as a repo you could clone.

### 0.2 The live origin (measured 2026-08-16)

`GET /v1/health` on `https://ihuuyvm4z6nfuktihnkey77fpy0eyrhj.lambda-url.ap-southeast-1.on.aws` returns:

```
ok=true · cluster_version "CockroachDB CCL v26.2.5" · database mainline_demo
deploy_chain_applied 271 / deploy_chain_files 271 · migrations_applied 0
schema_fingerprint ec9b1ce70a8df066e5763056c5ad9376800ef5df9362f7d0502b1dc7e7450339
```

`GET /v1/` returns a `no_route` 404 that **enumerates 17 declared resources** — a free, one-request route census a judge can run. That response is itself a census artefact and W1 owns quoting it.

### 0.3 The local cluster, `mainline_demo`, same v26.2.5 CCL build

Measured through `docker exec trappoint-crdb ./cockroach sql -d mainline_demo`:

| measured | count |
|---|---|
| application schemas | 6 — `trappoint`, `mainline`, `mainline_meas`, `mainline_ops`, `mainline_audit`, `mainline_qa` |
| base tables | 89 |
| views | 20 |
| **PL/pgSQL functions** | **26** |
| **PL/pgSQL procedures** | **2** |
| **triggers** | **59** |
| **user-defined enum types** | **7** (`blame_basis` 4, `blame_state` 4, `control_delta` 5, `disposition_kind` 6, `prop_state` 6, `subject_state` 7, `virulence_class` 4) |
| **generated / STORED columns** | **8** |
| **VECTOR columns** | **4** + 1 `tsvector` (the brief's "5 live VECTOR columns" counts the tsvector; W5 must fix the wording) |
| **`cspann` vector indexes** | **3** |
| **partial indexes** | **6** |
| inverted / GIN indexes | 5 |
| total indexes | 178 (116 unique) |
| **tables with ROW LEVEL SECURITY** | **4**, all 4 also `FORCE` |
| **RLS policies** | **25** |
| composite (multi-column) foreign keys | 15+, including three-column `legal_edge` / `cr_legal_edge` |

Three of the eight generated columns are load-bearing and **badly under-claimed**:

```
mainline.event_cue.tsv          →  to_tsvector('english', cue_text)
mainline.permit_event.chain_digest →  digest(prev_digest || payload::STRING::BYTES, 'sha256')
mainline.cr_event.chain_digest     →  digest(prev_digest || payload::STRING::BYTES, 'sha256')
```

That is **a cryptographic hash chain computed by the database as a STORED column**, not by the application. A CockroachDB judge would find that impressive and we currently say nothing about it.

The vector indexes and their prefix rule, verbatim from `pg_indexes`:

```
ce_ann         ON mainline.clause_embedding    USING cspann (site_id, activity_root, embedding vector_cosine_ops)
cue_scoped_idx ON mainline.event_cue_embedding USING cspann (site_id, scope_id, facet, emb vector_cosine_ops)
cue_sweep_idx  ON mainline.event_cue_coarse    USING cspann (tenant_id, emb_coarse vector_cosine_ops)
```

### 0.4 The AWS side, measured from Terraform

`infra/` declares, by resource type: 7 `aws_cloudwatch_metric_alarm`, 2 `aws_lambda_function`, 1 `aws_lambda_function_url`, 2 `aws_iam_role` + 2 policy + 2 attachment, 2 `aws_cloudwatch_log_group`, 1 `aws_cloudwatch_dashboard`, 1 `aws_sns_topic` + 2 subscriptions + 1 policy, 1 `aws_budgets_budget`, 1 `aws_kms_key` + alias, 1 `aws_cloudfront_distribution` + 2 OAC, 2 `aws_lambda_permission`.

**CloudFront is declared and NOT applied.** `infra/envs/demo/main.tf` lines 38–52 carry the real `terraform apply` transcript of 2026-08-10: AWS returned `403 AccessDenied — Your account must be verified before you can add new CloudFront resources`. Decision D1 inverted the default so the Lambda Function URL owns the hostname.

In the **live request path**, `verticals/mainline/apps/demo-api/src/mainline_demo_api/db.py` reaches SSM Parameter Store with **hand-rolled SigV4 and no boto3** (`_ssm_get_parameter`, `_signing_key`, lines 214–344), deliberately, so the deployment package's behaviour does not depend on which boto3 AWS ships. `retry.py:12` records the package is `psycopg-binary==3.3.4` **and nothing else**. That is a strong, checkable Technical-Implementation story nobody has written down.

### 0.5 The prior census exists — and it disagrees with our own brief

`evidence/tool-usage/aws-services.json` (12 rows: 6 EXERCISED / 5 DESIGNED / 1 NOT-AVAILABLE) and `evidence/tool-usage/crdb-features.json` (14 rows: 12 EXERCISED / 2 DESIGNED), generated by `scripts/submission/capture_tool_evidence.py`, narrated in `docs/TOOL-USAGE.md`.

The AWS file has **no row at all** for SNS, Budgets, Lambda Function URL, or CloudWatch Alarms/Dashboard as distinct entries — all four are real and applied. The CRDB file has no row for enums, generated columns, partial indexes, composite FKs, PL/pgSQL, full-text search, recursive CTEs, or `RETURNING`. **The census is under-claiming, exactly as the brief predicted.**

---

## 1. RULINGS

These bind every worker. Each names its authority.

### R1 — The Managed MCP Server is DEMONSTRATED. The task premise is wrong, and correcting it is the single highest-value act in this workstream.

**Authority: measured, `evidence/deploy/judge-run.json`, generated 2026-08-11T00:23:29Z.**

```
channels.mcp.ran            true
channels.mcp.endpoint       https://cockroachlabs.cloud/mcp
channels.mcp.protocol_version  2025-06-18
channels.mcp.cluster_id     7cfc9ee9-f9b4-413d-bcad-d81fca2c6c7e
channels.mcp.sql_identity   managed-mcp
channels.mcp.passed         15  of  total 16
verdict                     DIVERGED — KNOWN GAP
```

There **is** a recorded end-to-end MCP session driving a 16-question pack against the live Basic cluster, with `tools/list` returning 12 tools from server `cockroachdb-cloud 1.0.0`. The brief's claim that "there is no recorded end-to-end call — no `evidence/mcp/`" is a **directory-name check mistaken for an evidence check**. `crdb_managed_mcp` was promoted DESIGNED → EXERCISED on 2026-08-12 for exactly this reason and `docs/TOOL-USAGE.md:103` records the promotion.

Therefore: **no worker shall attempt a new MCP run, and no worker shall touch cloud credentials.** The remedy is discoverability, not evidence — W3 writes the pointer, the quote and the one-minute verification. The one thing that is still true and must be said plainly: `channels.mcp.passed` is **15 of 16**, the run's own verdict is `DIVERGED — KNOWN GAP`, and `managed_mcp_availability.credential_publishable` is **false**, so this channel cannot be handed to an anonymous judge. We report the 15/16 and the divergence. We do not round it off.

### R2 — The three states from the brief map onto the existing vocabulary; they do not replace it. And three is one too few.

**Authority: measured — the generator already emits EXERCISED / DESIGNED / NOT-AVAILABLE, and `evidence/tool-usage/*.json` is consumed by `docs/TOOL-USAGE.md` and the `claims.yml` / `submission.yml` ratchets.** Inventing a rival vocabulary would put two documents in the submission that disagree. The mapping is:

| census state | brief's phrasing | maps to generator verdict | example |
|---|---|---|---|
| **LIVE** | (a) exercised in this demo's request path | EXERCISED, plus a live-origin check | AWS Lambda, SSM Parameter Store, SERIALIZABLE, PL/pgSQL triggers |
| **REPO** | (b) exercised in this repository, not in that path | EXERCISED, no live-origin check | Amazon Bedrock, `cspann` vector search, ccloud CLI, Managed MCP |
| **APPLIED** | (c) applied as infrastructure | EXERCISED via a Terraform state or a console artefact | CloudWatch alarms, SNS topic, Budgets, IAM roles, KMS key |
| **DECLARED** | *(the fourth state the brief omits)* | DESIGNED | CloudFront — written, and **refused by AWS**, see R3 |

A four-state census is honest where a three-state one would have to lie about CloudFront. `NOT-AVAILABLE` (Bedrock Rerank) survives unchanged as a fifth, negative state and is worth keeping: a checked-and-absent row is a credibility asset.

### R3 — CloudFront is named only as designed-and-refused, with the refusal quoted.

**Authority: `infra/envs/demo/main.tf` lines 38–52, a real `terraform apply` transcript, plus `docs/deploy/RUNBOOK.md:26`.** Any sentence implying CloudFront serves the demo is false. The correct construction — and it reads as strength — is: *the distribution is written and Terraform-valid; AWS holds new CloudFront resources on this account pending verification; decision D1 gave the hostname to the Lambda Function URL so nothing could hold the URL hostage.*

### R4 — Bedrock keeps its existing construction and it is the model for every REPO-state row.

**Authority: measured — `grep boto3|bedrock` over `verticals/mainline/apps/demo-api/src/` returns only a comment in `db.py:26` explaining why boto3 is *not* imported.** Bedrock is real (`packages/trappoint-recall/src/trappoint_recall/eval/bedrock_backend.py`, `evidence/aws/embeddings/`, `evidence/aws/agent/live-run.json`) and is **not in the demo's request path**. Say exactly that. The repository already uses this construction and it reads as confidence, not hedging. Every (b)-state row copies it.

### R5 — The close block is ordered by judging axis one, not by service count.

**Authority: the tie-break quoted in §0.1.** CockroachDB-as-memory features lead; AWS breadth follows. A row that demonstrates *store → retrieve → act* outranks a row that adds a logo. W7 enforces the ordering.

### R6 — Every new row must be re-derivable by the generator.

**Authority: `scripts/submission/capture_tool_evidence.py` is the producer of `evidence/tool-usage/*.json`, and `docs/TOOL-USAGE.md` cites it by `#rows.<key>` anchors.** A hand-written census that the generator cannot reproduce will drift and then contradict itself in front of a judge. Workers propose rows **as prose plus the exact detector** (a grep pattern, a SQL probe, a file path) so a follow-up can add them to the generator. **No worker may weaken the generator, add `continue-on-error` or `|| true`, or relax a ratchet.**

### R7 — Undecidables are escalated, not guessed.

Anything requiring a `terraform apply`, a redeploy, an SSM write, a grant widening, or a new cloud credential is **out of scope by construction** and is written up as an open question for the founder. The standing `materialise_checks` / `exposure_receipt` INSERT gap stays open.

### R8 — "5 live VECTOR columns" is imprecise and gets corrected, upward-honestly.

**Authority: measured — 4 columns of type `vector` plus 1 `tsvector`.** The right claim is stronger than the wrong one: **4 VECTOR columns across 4 tables, 3 `cspann` distributed vector indexes with mandatory prefix columns, *and* a generated `tsvector` column giving full-text search in the same schema** — a hybrid lexical+dense memory. W5 owns the correction.

---

## 2. WHAT WE ARE UNDER-CLAIMING (the priority list for workers)

Ranked by what a CockroachDB judge would find impressive, highest first. Every item below was measured today and appears in **no** current submission document.

1. **59 triggers over 26 PL/pgSQL functions and 2 procedures** — the refusal logic lives in the database, not the app. This is the single strongest Agentic-Memory-Design fact in the project.
2. **RLS on 4 tables, all 4 `FORCE`, 25 policies** — plus conformance case `cf22_gate_under_force_rls`. The memory layer refuses even its owner.
3. **Generated STORED columns computing a SHA-256 hash chain** (`permit_event.chain_digest`, `cr_event.chain_digest`) — tamper-evidence as a column default.
4. **6 partial indexes used as invariants**, e.g. `one_live_disposition UNIQUE … WHERE retracted_by IS NULL` and `carriage_one_open` — a uniqueness rule the database enforces for a *subset* of rows.
5. **7 user-defined enum types** with 36 labels total.
6. **Composite foreign keys up to 3 columns** (`legal_edge`, `cr_legal_edge`) — legal-transition edges enforced by referential integrity.
7. **`cspann` prefix-column rule** — already partly told via `skills/designing-vector-recall-prefixes`, but not in the close block.
8. **Hybrid retrieval**: `tsvector` full-text + 5 inverted indexes alongside dense vectors.
9. **READ COMMITTED as a measured contrast to SERIALIZABLE** (`cf45_read_committed`) — we ship a conformance case that shows the difference.
10. **`AS OF SYSTEM TIME` as a deliberate REFUSAL** (`cf46_time_travel_cannot_reach`, `eval/splits.py`) — we use it and then prove it *cannot* do the thing people assume, bounded by `gc.ttlseconds=4h`. That is a more sophisticated claim than "we use time-travel queries".
11. **CCL v26.2.5 pinned, and the version is served by `/v1/health`** — a judge verifies our CockroachDB version in one request.
12. **271-file deploy chain applied 271/271 with a schema fingerprint** served publicly.
13. **Recursive CTEs** in `verticals/mainline/db/migrations/0034_event_edge.sql` and `db/queries/closure_write.sql`.
14. **Hand-rolled SigV4 to SSM with a single-dependency Lambda package** — see §0.4.
15. **SNS + Budgets + 7 CloudWatch alarms + a dashboard** — a Production-Readiness story with no row in the census.

## 3. WHAT WE MAY BE OVER-CLAIMING (audit targets)

- `crdb_managed_mcp` EXERCISED — **sustained** by R1, but must carry 15/16 and `credential_publishable: false`.
- `crdb_agent_skills` DESIGNED while the brief calls it "solid" — W3 resolves by measuring `skills/` and `.github/workflows/skills.yml`.
- `crdb_follower_reads` EXERCISED — W4 must find the artefact or downgrade it.
- `crdb_internal` EXERCISED — note the local cluster now **refuses** `crdb_internal` access with `42501` unless `allow_unsafe_internals = true`. Measured today. W4 must check whether any live path depends on it.
- `crdb_changefeed` DESIGNED — `packages/trappoint-migrate/README.md:253` explicitly forbids changefeeds in migrations. Keep DESIGNED; W4 states why, because the reason is good engineering.
- Anything in `docs/submission/MUST-NOT-CLAIM.md` — W7 diffs the census against it.

---

## 4. THE SEVEN WORKERS

Output paths are **disjoint**. No two workers write the same file. W7 runs last and reads W1–W6.

| # | worker | owns (writes) |
|---|---|---|
| W1 | AWS in the live request path | `docs/submission/census/aws-live-path.md` |
| W2 | AWS in the repo, and AWS applied as infrastructure | `docs/submission/census/aws-repo-and-infra.md` |
| W3 | The four contest-named CockroachDB tools | `docs/submission/census/crdb-four-tools.md` |
| W4 | CockroachDB transaction, isolation and time semantics | `docs/submission/census/crdb-transactional.md` |
| W5 | CockroachDB schema, type and index features | `docs/submission/census/crdb-schema-and-index.md` |
| W6 | CockroachDB as a programmable, self-defending database | `docs/submission/census/crdb-programmable.md` |
| W7 | Reconciliation, the master census, and the close block | `docs/submission/feature-census.md`, `docs/submission/census/close-block.md` |

**Every worker writes rows in this shape**, and a row missing any field is not finished:

```
### <feature name>
state:        LIVE | REPO | APPLIED | DECLARED | NOT-AVAILABLE
what it is:   one sentence, no marketing
where:        <absolute-in-repo path>:<line>  — or the infra resource
verify in 60s: <one command a judge can paste, and the expected first line of output>
say this:     <the exact sentence the close block may use>
never say:    <the adjacent false claim>
```

---

## 5. STANDING PROHIBITIONS — repeated in every brief

1. **No deploy.** Never `terraform apply`, never redeploy, never touch AWS state, never write an SSM parameter, never print or echo a credential. The orchestrator deploys.
2. **No commit.** Leave the tree for the orchestrator. Write only your owned files.
3. **No false claim.** If it did not run, it is not EXERCISED. If it is real but outside the demo's request path, say exactly that — Bedrock is the model (R4). One aspirational entry discredits the whole close block.
4. **No regression.** Baseline is **1070 collected / 1069 passed / 0 failed / 0 errors**; gate proof PROVEN caveat-free; `DEFAULT_MAX_RESPONSE_BYTES == 136 * 1024` may not move; the console bundle-headroom guard fails below 1,024 bytes. You are writing documentation — if a doc change can move any of those, you have gone out of scope.
5. **No grant widening.** The `materialise_checks` / `exposure_receipt` INSERT gap stays open. Not your call.
6. **No ratchet weakening.** `continue-on-error` and `|| true` are banned. Do not edit `HONESTY.md`, `CI-STATE.md`, `MUST-NOT-CLAIM.md`, or `scripts/submission/capture_tool_evidence.py`.
7. **Measure, do not recall.** Every state you assign is backed by a command you ran today and pasted the output of.

---

## 6. SEQUENCING

W1–W6 run in parallel; they share no output file and no input mutation. W7 starts when all six have written. Total wall-clock target: one pass, finished well inside 2026-08-17 so the film's close block can be cut from a settled document.
