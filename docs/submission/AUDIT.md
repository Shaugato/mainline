<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# AUDIT — every claim of this wave, read the way a rival team would

**Auditor:** adversarial pass · **Date:** 2026-08-16 · **HEAD at audit:** `c951558` plus the
uncommitted working tree · **Nothing was committed, applied, deployed or granted by this pass.**

Every number below was re-measured by this auditor against the live origin, the local cluster at
`postgresql://root@localhost:26257/mainline_demo`, the committed artefacts or the infrastructure.
Nothing is quoted from a document that asserts it. Where a claim and a measurement disagree, the
measurement is printed and the claim is struck.

**VERDICT: NOT READY — on documents, not on engineering.**

The suite holds at baseline, the gate proves caveat-free, the Managed MCP gap is genuinely closed,
and the ≥2-tool eligibility requirement is cleared three times over. But **eight published claims
fail their own one-command check**, and three of them sit in judge-facing documents. Every one is a
text fix costing minutes. NOT READY is a statement about the tree this morning, not about the
submission's prospects.

---

## 1 · THE REGRESSION GATE — no regression

`scripts/qa/regression_guard.py --suite-out qa/audit-suites.xml`, run by this auditor:

| family | result |
|---|---|
| **SUITES** | **1070 collected · 1069 passed · 0 failed · 0 errors · 1 skipped** — baseline exactly |
| **KERNEL** | `PROVEN`, `caveats` empty; `23514 gate_closed_when_issued`, `P0001 mainline.fn_permit_merge_gate`, `00000 ADMITTED` |
| **BOUNDS** | `136 * 1024 == 139264` unmoved; straddle `137939 < 139264 < 490373`; exactly 1 identity refusal |
| **LIVE** | `ok=true`, `deploy_chain_applied 271`, `gate_run_verdict PROVEN`, 4 beats, 0 mismatches |
| **SEED** | all 7 checks pass |
| **PRIVILEGES** | **1 FAIL** — `mainline.exposure_line INSERT`, `mainline.exposure_receipt INSERT` |

**The one FAIL is the sanctioned standing gap**, not a regression: widening the write surface of an
unauthenticated endpoint is the founder's call and he has not made it. It is reported here so that
nobody reads `30 PASS / 1 FAIL` as new damage. Overall: **31 checks, 30 PASS, 1 known-open FAIL.**

Both use cases still drive against the live origin. `evidence/demo/live-semantics.json`, regenerated
`2026-08-16T12:26Z` with **no credential of any kind**, carries **26 of 26 claims holding** and
**9 of 9 cross-response identities holding**, verdict `PROVEN`. Re-measured independently by this
auditor: `GET /v1/health` → `ok true`, `deploy_chain_applied 271 of 271`, `schema_fingerprint
ec9b1ce7…`, HTTP `200` with no credential, `x-amzn-RequestId` present.

---

## 2 · THE MCP QUESTION — DEMONSTRATED, and honestly declared in every document but one

**The gap named in the brief is closed.** `evidence/mcp/` exists and is real. Verified by this
auditor by reading the artefacts, not the README:

* `session.json` — `initialize` HTTP `200`, protocol `2025-06-18` negotiated, `serverInfo
  cockroachdb-cloud 1.0.0`, 12 tools, `sql_identity managed-mcp`, `bound_database mainline_demo`,
  cluster header matches the pin. `credential/value_recorded false`, `publishable false`.
* `read_only` — 3 write verbs on the live tool list, **0 called**, and the prohibition is *enforced*
  by an `httpx` request hook that aborts before transmission, not promised in prose.
* `pack-run.json` — `passed 15`, `total 16`, `exit_code 1`, `verdict DIVERGED — KNOWN GAP`. The one
  FAIL (`N01`) is preserved with its cause stated: `mainline_qa` **is** readable by the
  `managed-mcp` identity, which the pack asserted it was not.
* `credential_hygiene` — self-scanned, key in scope, **0 matches**.

**This is the strongest artefact the wave produced**, and the refusal to round `15/16` up to `16/16`
is what makes the other fifteen worth reading.

### The one document in the third state — this is the FAIL

`docs/submission/JUDGE-START.md` **Stop 5** reads:

> "it lets you read **our** CockroachDB Cloud cluster … Two published routes, both read-only, either
> one sufficient: 1. **MCP** — point any MCP client at the CockroachDB Managed MCP Server using the
> configuration in `MCP-CONFIG.md` §1. 2. **psql** …"

**That is false, and the project already knows it is false.** Four documents say the opposite:

* `SUBMISSION.json` — "The CockroachDB Managed MCP Server is a SEPARATE path and it **does not reach
  our data with any credential we publish**."
* `MCP-CONFIG.md` §0 — Path A credential is "**your own** … against **your own** cluster"; §1 is
  headed "pointing **your own** MCP client".
* `census/close-block.md` §7.2 — "the read-only endpoint a stranger can actually verify is the
  `mainline_judge` pgwire login — **not** the MCP one-liner".
* `census/close-block.md` §8 — bans the sentence *"judges can query our ledger over MCP"* by name.

`RULES-MATRIX.md:536` records that the "two paths" wording **was found and corrected in
`SUBMISSION.json` on 2026-08-16**. JUDGE-START.md carries the identical uncorrected wording. A judge
who follows Stop 5 route 1 cannot authenticate, and concludes the submission oversells. **A rival
team finding the project contradicting its own published correction is worse than the original
error.** Fix: Stop 5 has one published route to our ledger, and MCP-CONFIG.md §1 reproduces the
*mechanism* on the judge's own cluster.

---

## 3 · THE ≥2 TOOLS REQUIREMENT — eligibility is SAFE, and the close block overstates it

This is eligibility. Get it wrong and nothing else matters. **We claim four; three carry an
EXERCISED verdict with a committed transcript.**

| tool | census verdict | evidence this auditor checked |
|---|---|---|
| **CockroachDB Cloud + `ccloud` CLI** | `EXERCISED` | `evidence/ccloud/cluster-list.txt` — `ccloud auth whoami` + `cluster list -o json`, parsed not screen-scraped |
| **Managed MCP Server** | `EXERCISED` | `evidence/mcp/` (2026-08-16) **and** `evidence/deploy/judge-run.json` (2026-08-11) — two sessions, five days apart, same `15/16` |
| **Distributed Vector Indexing (C-SPANN)** | `EXERCISED` | measured live: **3** `cspann` indexes, **4** `VECTOR` columns; `42809` server refusal committed at `evidence/aws/ann/explain-unhinted.txt` |
| **Agent Skills** | **`DESIGNED`** | 2 authored skills + 1 de-branded; validator runs green (`3 skill(s), 0 error(s), 0 warning(s)`; `parser self-test: OK`) — **but no run is captured under `evidence/`** |

`RULES-MATRIX.md` **R6 states this correctly** and explicitly does not count Agent Skills. The floor
of two is cleared three times over.

**STRIKE.** `census/close-block.md` §3 says: *"All four are exercised in this repository with a
committed transcript."* Agent Skills has no committed transcript — the census's own basis string
says *"neither script's run is captured under `evidence/`"*. Say **three exercised, one shipped and
not evidenced**, or commit a transcript of the two assertion scripts (cheap: both run in seconds).

---

## 4 · EVERY CLAIM CHECKED — what held, and the eight that did not

### 4.1 Held, measured by this auditor

**On the cluster:** 26 PL/pgSQL functions (25 `mainline` + 1 `trappoint`) · 2 procedures · 39
triggers · 17 tables carrying `fn_refuse_mutation` · 4 `relforcerowsecurity` · 25 policies · 461
CHECK constraints · 19 multi-column FKs · 8 `GENERATED ALWAYS` columns · 4 `VECTOR` · 1 `tsvector` ·
3 `cspann` · 5 `gin` · 6 partial indexes · 14 `mainline_audit` views. **Every one matches the close
block.**

**In the tree and the infra:** `boto3` → 3 hits, **all comments** · `precondition {` → **7** ·
`aws_lambda_function` → **2** · alarms **7** (4 `module.api` + 3 `module.guard`) · SNS topic, topic
policy, subscription and `aws_budgets_budget` all present in `module.guard`'s 13 planned resources ·
plan `24 to add` matches `APPLIED.md`'s `24 created`, so **all seven alarms, the SNS topic and the
budget were applied**.

### 4.2 Struck or forced to re-state — **8**

> Zero would have been a suspicious answer. These are ranked by what they cost if a judge finds them.

**S1 — `census/close-block.md:246`, row 12, tagged LIVE. The published check contradicts the
published answer.** Card says: `SELECT rolname, rolcanlogin FROM pg_roles WHERE rolname LIKE
'mainline%'` → *"nine rows, `rolcanlogin` false on all nine"*. **Measured: 5 rows, and 2 of them
CAN log in** (`mainline_api`, `mainline_judge`). Worse — `mainline_judge` is *the credential this
submission publishes to judges*, so the card's own check refutes the card using the submission's
headline login. The **substance is true**: the correct predicate, which the source worker file
`census/crdb-programmable.md:827` still carries, is the explicit nine-name `IN` list —
`mainline_migrator, mainline_owner, agent_gate, agent_projector, agent_recaller, svc_disposition,
mainline_auditor, auditor_ro, quality_assurance` — and this auditor measured it: **9 rows, `canlogin`
false on all nine.** The `LIKE 'mainline%'` corruption was introduced when the worker file was merged
upward, and it is in **`docs/submission/feature-census.md:281` as well**. Fix both: restore the `IN`
list. (For completeness: `rolname LIKE 'agent\_%'` returns **10**, not nine, all NOLOGIN — so
"nine" is only correct against the named list.)

**S2 — `docs/submission/JUDGE-START.md` Stop 5.** MCP presented as a published read-only route to our
ledger. Struck; see §2.

**S3 — `docs/submission/VIDEO-KIT.md:497` — stale to the point of being false, and it is *shooting*
guidance.** It reads: *"Everything else in the AWS column — Lambda, SSM, CloudWatch — is **declared
in Terraform and not applied**"* and instructs the narrator *"**Two of ten**, named. Say those two."*
The apply happened **2026-08-14**. The census now reads **12 rows, 6 EXERCISED**, including Lambda,
IAM, SSM and CloudWatch. A narrator following this line would understate the submission on camera and
contradict `DEVPOST.md`, `close-block.md` and `APPLIED.md`. Struck.

**S4 — `docs/submission/VIDEO-KIT.md` §0.1 shot table describes a film that no longer exists.** It
lists 25 shots `s01`–`s25` totalling `171 s / 2:51`, closing on `s22-readiness-strip` /
`s23-honesty-card` / `s24-rubber-stamp` / `s25-end-card`, and includes **`s19-beat5-mcp-connect`**.
The current spine — `docs/demo/film/SPINE.md:197`, dated this wave — is **`148 s demo · 22 s close ·
2 s end card · 172 s · 2:52`**, structured `B0`–`B10` then `K1`/`K2`/`K3`. SPINE.md:216 says it in
terms: *"Any document still in-pointing the naming block at `2:00` is describing the pre-revision
film."* VIDEO-KIT.md is that document, and it was touched this wave without being reconciled. Struck
as a description of the current film.

**S5 — `census/close-block.md` §3, "All four are exercised … with a committed transcript."** Agent
Skills is `DESIGNED`. Re-stated; see §3.

**S6 — `census/close-block.md` §8, the EventBridge row.** It claims `grep -rn
"aws_cloudwatch_event\|aws_scheduler" infra` *"returns **nothing**"*. Run verbatim it returns **three
matches** — the vendored AWS provider binaries under `.terraform/`. The *conclusion* is right (no such
resource exists; `--include=*.tf` returns nothing, exit 1) but the **published command does not
produce the published output**, on a card whose entire premise is one-command falsifiability.
Re-state with `--include=*.tf`.

**S7 — the brief's own status table: "5 live VECTOR columns."** Measured: **4**. The census
(`close-block.md` row 10, `crdb-features.json`) says 4 and is correct. Re-stated so nobody carries
the 5 onto a card.

**S8 — `census/close-block.md` §7.1's card cut is not implemented and cannot be, as written.** Its
line 5 is *"All four contest CockroachDB tools: Managed MCP 15/16 · C-SPANN · ccloud · two Agent
Skills."* **No such line exists in `docs/demo/film/VO-CLOSE.md` §4.1**, which is the film authority
and states *"Every word below is the committed 50 s text."* VO-CLOSE §0.5 further rules **"no line
may be added to `k2`"**, and §4.2 excludes C-SPANN by name. Two documents from the same wave
prescribe different content for the same 22 seconds. Re-stated as unimplemented — see §5.

### 4.3 True, applied, and **absent from the census** — not struck, but not covered either

`evidence/tool-usage/aws-services.json` carries **12 rows and no row for SNS, no row for AWS
Budgets, and S3 only as `aws_s3_object_lock` (DESIGNED)**. The film's `k2` card names all three:
*"Amazon S3 — Terraform state · versioned · SSE-S3 · public access blocked"* and *"CloudWatch alarms
+ SNS + AWS Budgets"*. All three are **genuinely applied** — this auditor confirmed the SNS topic,
subscription, policy and `aws_budgets_budget` in the 24-resource apply, and `APPLIED.md` records the
state bucket. The card is also carefully scoped (it says *state* bucket, not evidence store).

So this is a **census coverage gap, not a false claim**: three services will be on screen that the
artefact a judge is pointed at does not list. Either add three rows to the generator, or have the
card cite `evidence/deploy/APPLIED.md` and `cost/plan-shape.json` as it already does at row 22.

*(Note, low severity: `APPLIED.md` says "three alarms", `close-block.md` says "seven". Both are true
at different scopes — 3 guard, 4 api. A judge reading both may not see that.)*

---

## 5 · THE FILM'S CLOSE — it fits 22 s, and it names **zero** CockroachDB tools

**Timing: PASSES.** `VO-CLOSE.md` §0.2 and SPINE.md agree — the naming block is **22 s in three
cards** (`K1` 6 s · `K2` 10 s · `K3` 6 s), **34 words at 1.55 w/s**, `148 + 22 + 2 = 172 s = 2:52`
against a 180 s rule and a 176 s CI cut. Margin: 8 s to the rule, 4 s to the build.

**States: correct for everything named.** `k2`'s AWS half separates *"IN THIS REQUEST"* (Lambda,
Function URL, SSM, IAM) from *"IN THE APPLY THAT CREATED IT"* (S3 state, CloudWatch+SNS+Budgets), and
boxes Bedrock as *"EXERCISED IN THIS REPOSITORY. IT IS NOT IN THIS REQUEST PATH."* — the exact
construction the brief asks for, and it reads as confidence. CloudFront, KMS, X-Ray and EventBridge
are all correctly absent, each with a stated reason. **No aspirational entry found on any card.**

**And here is the finding.** Counted off the committed overlay text:

* `k2`'s **AWS half names seven services**.
* `k2`'s **CockroachDB half names zero of the four contest tools.** It spends its 10 seconds on SQL
  features — `SERIALIZABLE`, a CHECK constraint, a trigger function, an enum, composite FKs, a
  recursive CTE, `42501`. All true, all good, none of them a *tool*.
* `k1` and `k3` name none either. **`MCP` appears nowhere in `VO-CLOSE.md`'s overlay text.**
* The current spine has **no MCP beat**: `B0`–`B10` are the permit story. (`s19-beat5-mcp-connect`
  exists only in the superseded VIDEO-KIT table — S4.)

So **the wave's single best artefact never reaches the screen**, and the closing card of a
CockroachDB hackathon film gives AWS seven names and CockroachDB none. There is no Functionality-rule
exposure — nothing undepicted is claimed — but on the axis that breaks ties this is the largest
unforced loss in the submission.

---

## 6 · THE UNANSWERED SCORING HOOKS — recovered **and answered**, not merely acknowledged

`JUDGING-AXES.md:33` states the finding and §§1–5 each **open by quoting the criterion's second
sentence**. All five are present (lines 97, 191, 308, 421, 581). Better: four of them are **answered
on screen**, on the `k3` criterion rail, arriving whole under R-3:

| criterion's second sentence | the clause on the rail |
|---|---|
| *"what makes agentic systems different from traditional apps?"* | the database is in the reasoning loop, as the thing that constrains the agent |
| *"Does the agent use the tools correctly and safely?"* | `persisted: false` — this endpoint cannot write |
| *"more than toy queries … at real scale?"* | transactional state, read inside the same `SERIALIZABLE` transaction as the decision — and no scale is claimed |
| *"resilience, access control, and what happens when things go wrong?"* | the refusal itself; `42501` on 256/256 ungranted pairs; a ledger that publishes what did not run |

**This is answered.** `VO-CLOSE.md` §0.3 also records what the compression cost — 118 → 24
clause-seconds of rail adjacency — rather than dressing it up. Nothing to fix.

---

## 7 · THE HONEST ANSWER TO THE FOUNDER'S QUESTION

**What this wave actually bought.**

1. **The MCP gap is closed, properly.** `evidence/mcp/` is the most agentic artefact in the
   repository: our memory layer interrogated through a surface *Cockroach Labs wrote and we did not*,
   with the server doing the refusing on the negatives, every statement screened before transmission,
   and the one failure published rather than rounded. This is worth real points on axis one.
2. **Six README sentences became 26 anonymous verified claims.** `live-semantics.json` — 26/26 and
   9/9 cross-response identities, no credential — converts prose into something a judge falsifies
   with `curl`. That is the correct shape for a Functionality-rule world.
3. **The census became machine-derived with resolving anchors.** All 26 rows carry
   `anchor_resolved.resolves: true` and `subject_holds: true`. That is why this audit could check it
   in minutes instead of hours.

**What it did not buy.** *None of it reached the film.* Not the MCP transcript, not the four tools,
not the live-semantics claims. The submission got stronger on paper and did not change by one frame
on camera. And the wave left **five documents disagreeing with each other**, two of them the first
things a judge opens.

**The highest-value remaining action, which nobody has proposed.** Everyone has been arguing about
what *evidence* to add. The binding constraint is no longer evidence — it is **the ten seconds of
`k2`'s CockroachDB half.** That card currently spends its whole budget on SQL features and none on
the four contest tools, while the AWS half beside it names seven services. On a lexicographic
tie-break where *Agentic Memory Design* is first, **rebalancing those ten seconds is worth more than
any new artefact anyone can produce in the time left** — the evidence already exists and is already
committed; it simply is not on screen. `k3` has 0.7 s of air and `VO-CLOSE.md` §0.5 forbids growing
`k2`, so this needs a ruling, not a rewrite.

---

## 8 · THE THREE THINGS MOST WORTH DOING, RANKED

**1 · Fix the three judge-facing contradictions. (~30 minutes. Do this first, today.)**
`JUDGE-START.md` Stop 5 (S2), `close-block.md:246` + `feature-census.md:281` role predicate (S1),
and `close-block.md` §3's "all four exercised" (S5). **Why it beats everything else:** each is
falsifiable by a judge in one command, each is in a document a judge opens before the video, and S1
and S2 are cases of the project **contradicting its own published correction** — the one failure mode
that reads as carelessness rather than candour and puts the credibility of the other 40 verified
numbers in question. Cost is minutes; the downside it removes is unbounded.

**2 · Get CockroachDB's tools onto the closing card — Managed MCP at minimum. (Needs a W1 ruling.)**
Today the close names 7 AWS services and 0 CockroachDB tools (§5). **Why it beats #3:** axis one is
lexicographically first and this is the only remaining change that alters what a judge *sees* about
agentic-memory depth. The evidence is already committed and already honest — `Managed MCP · 15/16 ·
DIVERGED, published` is one line. `VO-CLOSE.md` §0.5 forbids adding to `k2`, so route it through
`k3`'s 0.7 s of air or reopen §0.5 explicitly. **Do not shoot until this is decided** — it is cheap
before the take and expensive after.

**3 · Reconcile `VIDEO-KIT.md` with `SPINE.md` before the shoot. (~1 hour.)**
VIDEO-KIT still carries the 25-shot pre-revision structure, an `s19-beat5-mcp-connect` that no longer
exists, and §497's instruction to say Lambda/SSM/CloudWatch are *"not applied"* and to name *"two of
ten"* (S3, S4). **Why it beats adding SNS/Budgets census rows (§4.3):** a wrong shooting document
produces a wrong film, and the film is the artefact the Functionality rule binds — *"must function as
depicted in the video"*. A missing census row is a documentation gap a judge is unlikely to probe; a
narrator reading stale guidance understates the project on the record.

**Explicitly not recommended:** widening the `materialise_checks` / `exposure_receipt` grant to clear
the PRIVILEGES FAIL, and revoking the `mainline_qa` grant to turn `N01` green. Both would move a
number on submission eve at the cost of the thing that makes this submission credible — a negative
suite that has quietly gone green is the most dangerous artefact in a repository, because it reads as
the strongest. Leave both open and keep saying so.

---

*No file under `infra/` was read for anything but text. No AWS call was made. No credential was
printed. No grant was widened. No ratchet, baseline or honesty document was touched. Nothing was
committed.*
