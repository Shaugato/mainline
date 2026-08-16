<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# THE CLOSE BLOCK — the copy the film's closing block is cut from

**Worker:** W7 · **Date:** 2026-08-16 · **Authority:** [`../feature-census.md`](../feature-census.md),
which is itself merged from the six worker files in this directory.
**Ordering ruling:** the lead plan's **R5**.

Every line below is a sentence a judge can check in under a minute, and §6 gives the command and
the first line it prints for each one. Nothing here is aspirational: a line is on this card only
because a worker measured it today, and a line that is true of the repository but not reachable on
the live origin says **exactly where it is reachable** rather than being dropped or softened.

---

## 1. WHY COCKROACHDB COMES FIRST, AND WHY THAT IS NOT A COURTESY

The Official Rules break ties **lexicographically** across the five criteria, and *Agentic Memory
Design* is printed first:

> "if two or more Submissions are tied, the tied Submission with the highest score in the first
> applicable criterion listed above will be considered the higher scoring Submission."

So the close block is ordered by **what argues that the memory layer is a database that refuses**,
not by service count. A line that demonstrates *store → retrieve → act* outranks a line that adds a
logo. AWS breadth follows, and it follows because it is real, not because it is filler.

The rules also say a judge **may never run anything**:

> "Judges are not required to test the Project and may choose to judge based solely on the text
> description, images, and video provided."

That is why this page ships a **written cut** (§5) as well as a card and a spoken line. The close
block has to stand up as prose.

And the Functionality rule says the project **"must function as depicted in the video"** — which is
the whole reason for the state tags in §6. A line whose claim lives in a committed transcript
rather than on the origin says so on the card, in the line itself.

**Every line here passed three tests:** it was measured today; it survives
[`../MUST-NOT-CLAIM.md`](../MUST-NOT-CLAIM.md) read family by family; and a stranger with `curl`,
`grep` or a JSON parser can falsify it in under a minute.

---

## 2. PART A — COCKROACHDB IS THE MEMORY, AND THE MEMORY REFUSES

*Card lines, in order. The first four are the block; if only four lines fit, these are the four.*

> **1. The database refuses the merge — and it refuses the counter that lied to it.**
> Twenty-six PL/pgSQL functions and two stored procedures, welded by thirty-nine row-level
> triggers. On the live demo URL, `POST /v1/demo/gate-run` forces the projected obligation counter
> to zero out of band and re-attempts the merge; the gate re-derives the count from the base
> relations and refuses anyway. **The memory layer does not trust its own summary.**

> **2. And it refuses the cluster superuser.**
> Seventeen evidentiary tables carry an append-only trigger that raises unconditionally: measured
> as `root`, both `UPDATE` and `DELETE` are refused with `P0001` and the row count does not move.
> Four tables carry row-level security and all four `FORCE` it, which removes the owner's own
> exemption. Twenty-five policies.

> **3. Four beats — a read, two refusals, an admitted write — inside one `SERIALIZABLE`
> transaction that is rolled back.**
> The response tells you the isolation level, the two hybrid-logical timestamps that prove it was
> one transaction, and the savepoints that let a refusal undo only its own beat. And it tells you
> the rollback held: a before/after fingerprint over every table those beats can write.

> **4. The same crossed history: refused six times out of six at `SERIALIZABLE`, admitted six times
> out of six at `READ COMMITTED`.** One script, one paste, two numbers. That is why the memory
> layer is a database and not a cache — and it is why the isolation level is set explicitly on
> every attempt instead of inherited from a pool.

> **5. The event log is a SHA-256 hash chain that CockroachDB computes.**
> `chain_digest` is `GENERATED ALWAYS AS (digest(prev_digest || payload, 'sha256')) STORED`, so the
> application supplies the payload and is structurally incapable of choosing the digest — and a
> trigger refuses an append whose predecessor is not the real one.

> **6. An agent that writes the same obligation twice gets one row.**
> Not because the agent was careful: the row's identity is a SHA-256 the database computes from the
> row's own contents, and it is `UNIQUE`. The live URL serves that computed key.

> **7. Ask the live URL about a permit and it reads its own `CHECK` constraints out of the
> catalog** — constraint name, predicate text, and the current value of every counter the predicate
> mentions, reflected per request from `pg_constraint`. Nothing in the API knows them in advance.
> 461 CHECK constraints in the schema.

> **8. Refusal as a missing row.** The permit state machine is a three-column foreign key: eighteen
> transitions are legal, and the rest are not forbidden by a rule — they are **absent from a
> table**. An event claiming one is refused with `23503` by referential integrity.

> **9. A uniqueness rule that applies to a subset of rows.** Six partial indexes, two of them
> `UNIQUE`: a permit may accumulate any number of retracted clearances and at most one live one.
> There is no application code in that sentence.

> **10. Hybrid memory in one database, with no second engine and no sync job.**
> Four `VECTOR` columns, three `cspann` distributed vector indexes, and — in the same schema — a
> **generated** `tsvector` column with five inverted indexes beside it. One `EXPLAIN` shows both
> arms of the retrieval in one plan.

> **11. The refusal explains itself, from the same engine that refused.**
> `trappoint.explain_refusal` returns the minimal unsatisfiable subset and the nearest admissible
> alternative — and on the demo's *strongest* refusal it returns `not_computable` and names the
> capability gap instead of inventing a plausible answer.

> **12. Nine roles, none of which can log in.** The role that detects an obligation cannot create
> one, the role that creates one cannot dispose of it, and the role that certifies the books has no
> write path to them. Those nine are the **duty-separation lattice**, named one at a time in §6
> row 12, and they are **distinct by design from the two service logins that do connect** —
> `mainline_api`, which the Lambda authenticates as, and `mainline_judge`, the read-only login this
> submission publishes to judges. The lattice is NOLOGIN because a lattice that could log in would
> be a set of accounts; the two that can log in are the two that have to.

**Lines 1, 2, 3, 6, 7 and 12 are LIVE** — they run when a stranger sends one unauthenticated
request to the demo URL. **Lines 4, 5, 9 and 10 are exercised in this repository and on the pinned
cluster**, and the card says so in the same breath: *"measured on the cluster this demo reads."*
Line 8's constraint is in the schema and the rows it references are served publicly. Line 11 is
LIVE and the `not_computable` half is visible in the live response body.

---

## 3. PART B — THE FOUR CONTEST-NAMED COCKROACHDB TOOLS

The rules require **two**. We used **four**, and each one differently — which is the finding, not
the count. **Three of the four are exercised in this repository with a committed transcript** —
Managed MCP, C-SPANN and `ccloud`. **The fourth, Agent Skills, is `DESIGNED`: the skills are
shipped and not evidenced.** That is the census's own basis string, not a softening invented here —
`evidence/tool-usage/crdb-features.json` → `rows.crdb_agent_skills.verdict_basis` reads *"two skills
are on disk, each shipping an executable assertion script; neither script's run is captured under
`evidence/`, so they are shipped and not evidenced"*, and `.verdict` reads `DESIGNED`. **The floor of two is cleared three times over without it**, which is
exactly why nothing is gained by rounding it up.

And **none of the four is in the demo's HTTP request path**: that path opens a `psycopg` connection
and reads SSM. Saying so costs nothing, because what the three carry instead is a transcript
against the real managed cluster, which is a stronger artefact than a code path a judge cannot see.

> **13. CockroachDB Cloud Managed MCP Server — driven end to end, twice, five days apart.**
> Protocol `2025-06-18`, server `cockroachdb-cloud 1.0.0`, twelve tools, SQL identity
> `managed-mcp`. A sixteen-question pack through it: **fifteen of sixteen**, both times, verdict
> `DIVERGED — KNOWN GAP`. The one that failed is recorded, not rounded off — the MCP identity reads
> a view our pack asserted it could not, and the read-only login we *do* publish refuses that same
> statement at `42501`. **We do not hand out the MCP key: its own tool list can create a database.**

> **14. Distributed Vector Indexing — and the prefix rule enforced by the server, not by a
> comment.** Three `cspann` indexes with one, two and three prefix columns. C-SPANN keeps a
> separate K-means tree per distinct prefix value, so leave a prefix column unbound and CockroachDB
> refuses the query outright — **`SQLSTATE 42809`** — and we ship the refusal as evidence. Two of
> the pack's MCP questions came back as real plans carrying a `vector search` node and non-empty
> `prefix spans`: **tool 1 proving tool 2, over CockroachDB's own endpoint, with none of our code
> between the question and the answer.**

> **15. `ccloud` CLI, agent-ready — driven with `-o json` and parsed, not screen-scraped.**
> The committed transcript names the cluster the whole submission points at, and its cluster id is
> the same one the MCP session pins. We also publish the limit we hit: `0.6.12` has no
> non-interactive service-account auth, so headless paths use the Cloud REST API with the same key.

> **16. Two authored CockroachDB Agent Skills, Apache-2.0, shipped two ways** — the Agent Skills
> spec and a Claude Code plugin marketplace. Each ships a script that **fails when the guarantee
> does not hold**, and the lane is written to run the failing half first: nine unwelding rows
> against a throwaway CockroachDB node, four of which must ADMIT, plus nine planted violations each
> refused by name. A third skill is de-branded and **staged for contribution — not filed, and not
> merged.** **This is the one row of the four that is `DESIGNED` rather than `EXERCISED`, and it
> says so on the card:** the skills are on disk and the spec validator passes over them, but
> **neither assertion script's run is captured under `evidence/`** — they are *shipped and not
> evidenced*, and there is no transcript here for a judge to open. Line 16's check in §6 proves the
> validator, which is the claim; it does not prove a run, which is not.

---

## 4. PART C — AWS, AND THE THREE HALVES ARE NOT THE SAME CLAIM

> **17. The whole demo API is one Python 3.13 AWS Lambda in `ap-southeast-1`.** No web framework,
> no adapter, no API Gateway: a Lambda invocation is already a function call with a dict argument,
> so `app.handler(event, context)` is the server.

> **18. The hostname is a Lambda Function URL with `authorization_type = NONE`.** An anonymous
> `curl` with no signature, no credential and no header gets a `200` — which is exactly what the
> rules' freely-accessible requirement asks a judge to be able to do. HTTPS is terminated by AWS on
> its own certificate.

> **19. The Lambda's execution role can do two things: write its own log group, and read one named
> SSM parameter.** `ssm:GetParameter` on **one ARN** — not a prefix, not a wildcard — and
> `kms:Decrypt` narrowed by the encryption context naming that same parameter.

> **20. It reads that credential from SSM Parameter Store over a request it signs itself.**
> The deployment package's entire third-party dependency closure is `psycopg`: **no boto3, no
> botocore**, and SigV4 built from `hashlib` and `hmac` — deliberately, so the package does not
> depend on which SDK version AWS happens to ship. A test enforces it rather than a comment asking
> politely.

> **21. Every invocation is logged to a Terraform-managed CloudWatch log group** — and the handler
> enforces a per-invocation **log byte budget** on top, because a log group has retention and not a
> quota, and ingestion is the charged term. Under a flood the refusal path is the hottest path in
> the function.

> **22. A second Lambda exists whose only job is to stop the first one.** Seven CloudWatch alarms
> across four metrics and three timescales, one SNS **stop** topic, and a USD 25/month AWS Budget
> all publish the same meaning — *stop the demo* — and the responder's IAM role carries an explicit
> `Deny` on `DeleteFunctionConcurrency`, because a stop that can be undone by the thing being
> stopped is not a stop. **All of it applied on 2026-08-14; none of it has ever fired, and we say
> so.**

> **23. Amazon Bedrock is real in this repository and is not in the demo's request path.**
> Titan Text Embeddings v2 produced 2,060 real 1,024-dimension vectors in Sydney; they sit in
> CockroachDB `VECTOR(1024)` columns and are searched through a C-SPANN index with both prefix
> columns bound. Seven live Claude legs, each with an AWS request id, each recorded as a cassette
> that replays to a byte-identical decision. **The demo's Lambda imports `psycopg` and nothing
> else** — which is the same sentence as line 20, read from the other end.

> **24. Terraform refuses, at plan time, a configuration that would deploy cleanly and fail
> later** — including one precondition that refuses a self-countersignature **because the database
> refuses it**. That is the AWS half of this project deferring to the CockroachDB half.

---

## 5. PART D — THE TWO ABSENCES WE PUT ON THE CARD ON PURPOSE

A services list that omits what you checked and could not have is a list a judge cannot audit.

> **25. Amazon CloudFront is written, Terraform-valid, and has never been created.** AWS holds new
> CloudFront resources on this account pending verification — a `403 AccessDenied` we reproduced
> from a bare CLI call under `AdministratorAccess` — so decision D1 gave the hostname to the Lambda
> Function URL, and **nothing in this stack can hold the demo URL hostage.**

> **26. Bedrock Rerank is not offered in our region.** We checked, we published the control-plane
> listing that shows it, and we took no dependency on it. Listwise reranking runs on the Claude
> profile instead, and CockroachDB's own `vector_search_rerank_multiplier` governs the ANN side.

**And the honest limits, which belong in the same breath and cost nothing:**

> **27.** The corpus, the operator, the site and the incident were **authored for this
> repository**. The mechanism is real; the inputs are synthetic.
> **28.** Inference is in Sydney and the database is in Singapore, because the closer region is
> Advanced-tier only on CockroachDB Cloud. There is no end-to-end residency and the honesty card
> says so.
> **29.** Nothing distinguishes a considered disposition from a rubber stamp. We make the question
> unavoidable and the record precise; **we measure deliberation and we never accuse.**

---

## 6. EVERY LINE, ITS STATE, AND HOW A JUDGE FALSIFIES IT IN UNDER A MINUTE

`$ORIGIN` is the demo URL in `docs/submission/SUBMISSION.json`. Nothing in this table needs an AWS
account, a database credential, or a clone — except the five rows marked *cluster*, which need the
repository and Docker, and which name a committed artefact as the credential-free alternative.

| # | state | check | first line it prints |
|---|---|---|---|
| 1 | **LIVE** | `curl -sX POST -H 'content-type: application/json' -d '{}' $ORIGIN/v1/demo/gate-run` | `verdict PROVEN`, 4 beats; beat 3 `sqlstate P0001`, constraint `mainline.fn_permit_merge_gate` |
| 2 | **LIVE** (welded schema) · superuser refusal measured on cluster | `SELECT count(DISTINCT tgrelid) … proname='fn_refuse_mutation'` → **17**; `SELECT count(*) FROM pg_class WHERE relforcerowsecurity` → **4** | `17` · `4` |
| 3 | **LIVE** | same gate-run: `transaction.isolation`, the two logical timestamps, `persistence_check.identical` | `SERIALIZABLE`; opened == closed; `identical true` |
| 4 | **REPO** — the script is in `census/crdb-transactional.md` §7.1 | run it against the local node | `SERIALIZABLE : 40001 in 6 of 6 crossed races` / `READ COMMITTED : 40001 in 0 of 6` |
| 5 | **LIVE** (column + trigger both in the deployed schema) | `SELECT count(*) FROM information_schema.columns WHERE is_generated='ALWAYS'` → **8**; the two `chain_digest` expressions contain `digest(` and `'sha256'` | `8` |
| 6 | **LIVE** | `GET $ORIGIN/v1/permits/{permit_id}/blocking-checks` → `dedupe_key`, 64 hex characters, byte-identical to the cluster's generated column | a 64-hex `dedupe_key` |
| 7 | **LIVE** | `GET $ORIGIN/v1/permits/{permit_id}` | 7 reflected CHECK constraints with predicate text and live counter values |
| 8 | **REPO** (the constraint) · **LIVE** (the rows it references) | `SELECT count(*) FROM pg_constraint WHERE contype='f' AND array_length(conkey,1)>1` → **19** | `19` |
| 9 | **REPO** *(cluster)* | `SELECT count(*) FROM pg_indexes WHERE indexdef ILIKE '%WHERE%'` → **6**; `EXPLAIN` prints the literal words `(partial index)` | `6` |
| 10 | **REPO** *(cluster)* | `… crdb_sql_type ILIKE 'VECTOR%'` → **4**; `… data_type='tsvector'` → **1**; `… indexdef ILIKE '%cspann%'` → **3**; `… ILIKE '%USING gin%'` → **5** | `4 · 1 · 3 · 5` |
| 11 | **LIVE** | same gate-run: beat 2's `naa` is populated; beat 3's is `null` with `naa_reason "not_computable"` | `not_computable` |
| 12 | **LIVE** | `SELECT rolname, rolcanlogin FROM pg_roles WHERE rolname IN ('mainline_migrator','mainline_owner','agent_gate','agent_projector','agent_recaller','svc_disposition','mainline_auditor','auditor_ro','quality_assurance') ORDER BY 1;` — the lattice **by name**, the predicate preserved at `census/crdb-programmable.md:827`. The two service logins `mainline_api` and `mainline_judge` are deliberately outside the list and both **can** log in; a wildcard over the `mainline` prefix answers a different question and is not this check | nine rows, `rolcanlogin` false on all nine |
| 13 | **REPO** — committed transcript | `python -c "import json;d=json.load(open('evidence/mcp/pack-run.json'));print(d['passed'],'/',d['total'],d['verdict'])"` | `15 / 16 DIVERGED — KNOWN GAP` |
| 14 | **REPO** — committed transcript | `grep -n "prefix spans" evidence/aws/ann/explain-hinted.txt`; and `evidence/aws/ann/explain-unhinted.txt` Appendix B for the `42809` refusal | the `prefix spans` line; `REFUSED BY THE SERVER — SQLSTATE 42809` |
| 15 | **REPO** — committed transcript | parse `evidence/ccloud/cluster-list.txt` as JSON | `mainline-dev v26.2.5 AWS ap-southeast-1` |
| 16 | **REPO** | `python skills/validate-spec.py skills/ --strict`; `… assert_gate_refuses.py --parser-self-test` | `3 skill(s), 0 error(s), 0 warning(s)`; `parser self-test: OK` |
| 17 | **LIVE** | `curl -si $ORIGIN/v1/health \| head -1` | `HTTP/1.1 200 OK` (with `x-amzn-RequestId` in the headers) |
| 18 | **LIVE** | `curl -s -o /dev/null -w '%{http_code}\n' $ORIGIN/v1/health` **with no credential** | `200` |
| 19 | **LIVE** | `sed -n '276,322p' infra/modules/demo-api/main.tf` | `data "aws_iam_policy_document" "dsn_access" {` |
| 20 | **LIVE** | `grep -rn boto3 verticals/mainline/apps/demo-api/src/mainline_demo_api/*.py` | 3 hits, **all of them comments** |
| 21 | **LIVE** (declaration + AWS-issued invocation id; reading an event needs the account) | `curl -sD- -o /dev/null $ORIGIN/v1/health \| grep -i x-amzn-requestid` | `x-amzn-RequestId: <uuid>` — and eleven more are already committed in `evidence/demo/live-beats.json` |
| 22 | **APPLIED** — created, never fired | `evidence/deploy/APPLIED.md:14`; `len(evidence/deploy/cost/plan-shape.json#/alarms)` → **7**; `grep -rn 'resource "aws_lambda_function"' infra` → **2** | `24 created, 0 changed, 0 destroyed` · `7` · `2` |
| 23 | **REPO** — real, and not in the request path | `python scripts/aws/agent_live.py --verify`; `python scripts/aws/verify_evidence.py` | `verdict: PASS`, `replay hashes equal: True`; `1235 assertions across 40 of 40 declared invariants. PASS` |
| 24 | **LIVE** (the preconditions are in the applied module) | `grep -c "precondition {" infra/modules/demo-api/main.tf` | `7` |
| 25 | **DECLARED** — refused by AWS | `sed -n '38,52p' infra/envs/demo/main.tf` | the verbatim `AccessDenied: Your account must be verified before you can add new CloudFront resources` |
| 26 | **NOT-AVAILABLE** | `python -c "import json;print(json.load(open('evidence/tool-usage/aws-services.json'))['rows']['aws_bedrock_rerank']['verdict'])"` | `NOT-AVAILABLE` |
| 27–29 | limits, stated | `docs/HONESTY.md`, `verticals/mainline/demo/DEMO-HONESTY.md` | — |

**One command underwrites nine of these rows.** `GET $ORIGIN/v1/health` returns, with no
credential: `ok true`, `cluster_version "CockroachDB CCL v26.2.5 …"`, `database mainline_demo`,
`deploy_chain_applied 271` of `deploy_chain_files 271`, and a `schema_fingerprint`. It is the same
fingerprint a transcript committed on 15 August recorded from the same Function URL — so the
deployed database is the one the evidence describes, and a judge can falsify that in one `curl` and
one `grep`.

---

## 7. THE THREE CUTS

### 7.1 The static card — a written/press-kit fallback, **not** the film's overlay

**This file does not prescribe the film.** The sole authority for what appears on screen in the
closing block is [`../../demo/film/VO-CLOSE.md`](../../demo/film/VO-CLOSE.md) §§2–5 together with
[`../../demo/film/ONSCREEN-TEXT.yaml`](../../demo/film/ONSCREEN-TEXT.yaml) `k1`/`k2`/`k3`, which
carry the committed overlay strings; where this section and those files differ, **they win and this
one is wrong.** The six lines below are a **static card for the press kit and the written
submission** — a slide, a README banner, a still — and they were never implemented as film text.

Set Part A lines **1–4** first and large; then Part B as four short tool names with their one
number each; then Part C as a single stack; then Part D. If the static card can hold only six
lines:

```
The database refuses the merge — and refuses the counter that lied to it.
And it refuses the cluster superuser. Seventeen tables. root cannot edit an event.
Four beats, two refusals, one SERIALIZABLE transaction, rolled back.
Refused 6/6 at SERIALIZABLE. Admitted 6/6 at READ COMMITTED.
Four contest CockroachDB tools. Three exercised with transcripts: Managed MCP 15/16 · C-SPANN 42809 · ccloud. Agent Skills: DESIGNED.
One Python Lambda, one Function URL, no SDK in the package. Bedrock is in the repo, not in the path.
```

Line 5 is corrected here regardless of where the block is used: a line that says *"all four
exercised"* is false in a press kit exactly as it would be on a frame.

### 7.2 The spoken line

Six seconds, and it is the sentence the whole film has been earning:

> *"Everything you just saw, the database did. Repository, demo URL, read-only endpoint — verify
> it yourself."*

The **read-only endpoint a stranger can actually verify** is the `mainline_judge` pgwire login in
`docs/deploy/JUDGE-PACK.md` §2 — **not** the MCP one-liner, which needs the viewer's own Cloud
service-account key. If `claude mcp add` appears on the card at all it must be labelled *"your own
cluster."*

### 7.3 The written cut (Devpost, **239 words**, counted) — because a judge may never press play

> MAINLINE puts the refusal inside CockroachDB. Twenty-six PL/pgSQL functions and two procedures,
> welded by thirty-nine row-level triggers, refuse a merge that the projected counter says is
> legal — because the gate re-derives the count from the base relations instead of trusting its own
> summary. Seventeen evidentiary tables refuse `UPDATE` and `DELETE` from `root` itself; four
> tables `FORCE` row-level security so the policy binds the owner. The four demo beats — a read,
> two refusals, an admitted write — run inside one `SERIALIZABLE` transaction that is rolled back,
> and the response hands you the isolation level, both hybrid-logical timestamps and the rollback
> fingerprint. The same crossed history is refused six times out of six at `SERIALIZABLE` and
> admitted six times out of six at `READ COMMITTED`; that measurement is why this memory layer is a
> database. We used all four contest CockroachDB tools, three with a committed transcript: Managed
> MCP end to end at fifteen of sixteen with the divergence published, C-SPANN vector indexes whose
> prefix rule the server enforces at `42809`, and `ccloud -o json`. The fourth, two authored Agent
> Skills, is shipped and validated but has no committed run, so we call it designed. On AWS: one
> Python Lambda, one Function URL with `authorization_type NONE`, SSM reached by hand-rolled SigV4
> with no SDK in the package, CloudWatch, SNS, Budgets and a cost guard applied. Bedrock is real in
> the repository and is deliberately not in the request path.

---

## 8. BANNED FROM THIS CARD — the lines that would cost more than they buy

Each of these is checkable by a judge in one command, and each would discredit the rest.

| never say | why | say instead |
|---|---|---|
| "CloudFront serves the demo" · "behind a CDN" · "at the edge" | no distribution exists; AWS refused to create one | line 25 |
| "We use EventBridge" | `grep -rn --include=*.tf "aws_cloudwatch_event\|aws_scheduler" infra` prints **no output and exits 1**. `--include=*.tf` is load-bearing and this row was struck once for omitting it: without the filter the same grep matches **three vendored `terraform-provider-aws_*_x5.exe` binaries** under `infra/**/.terraform/` and **exits 0**, which says nothing about our configuration. **This row is dropped from the close block on purpose** — it is the one AWS line a judge could falsify with a single grep, and the list is strong enough without it | say nothing |
| "AWS KMS is on the request path" | the applied SSM parameter's **type has never been read back**; if it is a plain String no KMS call happens. **KMS is deliberately absent from every line above** | say nothing until the one read-only command is run |
| "Distributed tracing with X-Ray" | the trace header is the Lambda service's; there is no tracing configuration in `infra/` | say nothing |
| "The MCP pack passes" · "judges can query our ledger over MCP" | it exits 1 at 15 of 16, verdict `DIVERGED — KNOWN GAP`; `credential_publishable` is **false** | line 13 |
| "Our skill was merged upstream" · "we contributed a skill to CockroachDB" | nothing is merged and nothing is filed; the claims-grep fails the build on the first sentence | line 16 — staged, and claim the filing, never the merge |
| "The conformance suite passes / has been demonstrated" | it has not been. Two cases are captured instead by `scripts/proof/gate_refusal.py` | that smaller, true claim |
| "The demo does an ANN search when you click it" | no ANN query runs in the request path | line 14 — the indexes are live in the database, the search is evidenced |
| "Five VECTOR columns" | four, plus a `tsvector` — and saying so is the **better** claim | line 10 |
| "59 triggers" flat | 39 trigger objects over 59 trigger-event pairs; a judge running the obvious count gets 39 | line 1 |
| "Row-level security defends against an administrator" | banned by name in `claim_hygiene`; RLS is evaluated by the same server that principal owns | line 2 — it removes the **owner's** exemption, which is what `FORCE` means, and against an administrator the claim is tamper-evidence |
| "The database refuses a defeater code that was never offered" | `mainline.disposition` has **no** foreign key onto `mainline.defeater_option`; that one refusal is the application's | nothing — and this is the line a founder three minutes into saying *"the database refuses"* will say once too often |
| "Our alarms caught…" · "the budget caps our spend" · "the kill switch was tested end to end" | applied and unexercised; Budgets evaluates on a documented lag and caps nothing | line 22, including its last clause |
| "These screens are the deployed console" | the operator capture states its own target: `127.0.0.1:8741`, `emulator_header local_furl`, `is_the_deployed_url false` | "filmed against a local emulator of the Function URL, running the same handler module the Lambda runs" |
| "End-to-end Australian data residency" | forbidden by name in the register and on the camera-strings list | line 28 |
| Any latency number as a product characteristic | every timing in this repository is local Docker; there is no p50 and no p99 for the cross-region hop | say nothing about speed |

---

## 9. WHAT CHANGED IN THIS DRAFT, AND WHY

| change | authority |
|---|---|
| **The Managed MCP Server moved from "configured" to demonstrated**, carrying 15 of 16, `DIVERGED — KNOWN GAP` and `credential_publishable: false` in the same sentence | R1 — two committed transcripts, five days apart, agreeing |
| **"5 live VECTOR columns" became 4 VECTOR + 3 `cspann` + a generated `tsvector`** | R8 — measured twice today; the corrected claim is the stronger one |
| **CockroachDB now leads the block and AWS follows** | R5 — the lexicographic tie-break, with *Agentic Memory Design* printed first |
| **EventBridge dropped from the card entirely** | over-claim O2 in the master census: there is no such resource in the tree |
| **KMS left out of every line** | over-claim O15: the applied parameter's type was never read back. The default is to leave it out |
| **Every REPO line now says where it *is* reachable** rather than being softened | the Functionality rule, and R4 — Bedrock's construction is the model |
| **The four AWS lines about the cost guard were merged into one (line 22)** and end with "none of it has ever fired" | R5 — a row that adds a logo outranks nothing, and an unexercised control that says so is worth more than four that do not |
| **§6 row 12's check became the explicit nine-name `IN` list with `ORDER BY 1`**, and §2 line 12 now names the two service logins (`mainline_api`, `mainline_judge`) that sit outside the lattice. **The answer did not move: nine rows, `rolcanlogin` false on all nine.** The wildcard predicate this row used to print returned five rows with two of them able to log in — one being `mainline_judge`, the login we publish — so the card's own check refuted the card | `AUDIT.md` §4.2 **S1** · predicate restored from `census/crdb-programmable.md:827` · both predicates re-measured today against the local cluster, twice (psycopg and `cockroach sql`). **The claim was not weakened to match the broken check** |
| **§3 no longer says "all four are exercised … with a committed transcript."** It says three exercised with a committed transcript and one — Agent Skills — **shipped and not evidenced**. Line 16 and the §7.3 written cut say the same in their own words; the count of four survives, the state of the fourth is stated | `AUDIT.md` §4.2 **S5** and §3 · the census's own `verdict_basis` in `evidence/tool-usage/crdb-features.json`, whose `crdb_agent_skills.verdict` is `DESIGNED`. **No skills run was captured or committed to promote the row** — the tool is stated in the state it is in. Stating the fourth tool's state grew the §7.3 cut by **20 words**; its header claimed *"~180 words"* while the cut already ran to **219**, so the header now carries the counted length, **239** |
| **§8's EventBridge row now prints `grep -rn --include=*.tf …` and its real result: no output, exit 1** — with the reason the filter matters (three vendored provider `.exe` matches, exit 0, without it) | `AUDIT.md` §4.2 **S6** · both forms run verbatim by this worker today. The row's whole premise is one-command falsifiability, so the command has to be the one that was run |
| **§7.1 stopped prescribing the film's card.** It now names `docs/demo/film/VO-CLOSE.md` §§2–5 and `docs/demo/film/ONSCREEN-TEXT.yaml` `k1`/`k2`/`k3` as the sole authority for the overlay, and re-labels its six-line block as a written/press-kit fallback for a static card. Its line 5 is corrected regardless of use: four named, three exercised with transcripts, Agent Skills `DESIGNED` | `AUDIT.md` §4.2 **S8** and close-card plan **R-C8** — two documents from one wave were prescribing different content for the same 22 seconds. `VO-CLOSE.md` is the film authority; this file defers |

**Suggestion for the orchestrator, not a change made here.** `docs/submission/VIDEO-KIT.md` still
tells the shoot to *drop the CloudWatch tile* from `s22-readiness-strip` because the alarms "have
not been created". They were created on 2026-08-14. The tile is now defensible with one honest
caption — *"seven CloudWatch alarms, one SNS stop topic, a USD 25 budget: applied, never fired"* —
and that file is outside this worker's two owned paths.
