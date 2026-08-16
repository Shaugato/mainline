<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# MCP REAL PLAN — turning the Managed MCP Server from *configured* into *interrogated*

**Lead:** managed-mcp lead. **Written:** 2026-08-16. **Submission closes:** 2026-08-18 17:00 EDT.
**Workers:** 6, disjoint paths, enumerated literally in §5.

---

## 0. The headline: the brief's premise was wrong, and measurement is what corrected it

The tasking said *"there is no recorded end-to-end call — no `evidence/mcp/`."* The second half
is true. **The first half is false**, and no worker may repeat it.

`evidence/deploy/judge-run.json` (generated `2026-08-11T00:23:29Z`) is a complete
sixteen-question judge-pack run driven over `https://cockroachlabs.cloud/mcp`: protocol
`2025-06-18`, `serverInfo {"name":"cockroachdb-cloud","version":"1.0.0"}`, `tools/list`
returning 12 tools, `sql_identity: "managed-mcp"`, **15 PASS of 16**, the one FAIL preserved
and the run's own verdict left at `DIVERGED — KNOWN GAP`. `evidence/deploy/judge-access.json`
carries the same handshake as `mcp_channel` with `reachable: true`.

So the Managed MCP Server is not an aspiration in this repository. It is an **exercised tool
with a committed transcript**, and `docs/TOOL-USAGE.md` §"Tool 3" already says so with a dated
promotion. What is actually wrong is narrower, sharper, and — because Agentic Memory Design is
the first criterion in a lexicographic tie-break — **more valuable to fix than a fresh
connection would have been**:

| # | the real defect | measured how |
|---|---|---|
| **D1** | **Our flagship MCP client cannot dial the live server.** `ToolDialect.statement = "statement"`; the live tool takes `query`. | `tools/list` inputSchema, today; and a live call with `statement` returns `{"code":0,"message":"must contain exactly one statement"}` |
| **D2** | Because of D1, `judge/cli.py run --via mcp` — the pack's own runner, with its envelope validator, drift check and truncation guard — **has never reached the live surface**. The Aug-11 transcript came from a 40-line ad-hoc client inside `judge_access.py`. | `scripts/deploy/judge_access.py:92-99`, `:336-338` |
| **D3** | The MCP evidence is **misfiled**. It lives under `evidence/deploy/`, whose name says deployment. A judge looking for the MCP tool does not find it. | `ls evidence/` — no `mcp/` |
| **D4** | The transcript is **five days stale** and predates the Lambda deploy, the console work and the current corpus. | `generated_at 2026-08-11` |
| **D5** | The **auditor persona and the budget prober have never run live.** These are the two modules that make this an *agentic-memory* demonstration rather than a connectivity check, and both are proven only against `httpx.MockTransport`. | `packages/mainline-mcp/README.md` "Verification status" |
| **D6** | `tests/integration/mcp/` still skips with a reason. The suites remain unexercised even though the endpoint is not. | `tests/integration/mcp/test_audit_surface.py:63-83` |
| **D7** | The film beat `s19-beat5-mcp-connect` (2:05, 8 s) is marked **"Declared, not run here."** The Functionality rule requires the project to function as depicted. | `docs/submission/VIDEO-KIT.md:1372` |

**D1 is the spine of this plan.** It is a six-field dataclass. Correcting it lights up D2, D5
and D6 at once, because `runner.py`, `auditor.py` and `budget.py` all dial through that one
object. The package's own README predicted this exact repair — *"isolated in one injectable
`ToolDialect` object rather than spelled inline in seven methods, so a live-surface difference
is a one-line change and never a hidden guess."* The design was right. Now we cash it.

---

## 1. What I measured myself, today, 2026-08-16

A read-only probe of the live endpoint, run from this machine with the repository's own
`CC_API_KEY` and cluster pin. No write verb was called. No credential was printed.

**Reachability — LIVE.**

```
initialize        HTTP 200   protocolVersion 2025-06-18
                             serverInfo {"name":"cockroachdb-cloud","version":"1.0.0"}
tools/list        HTTP 200   12 tools, byte-identical to the 2026-08-11 list
select_query      HTTP 200   SELECT current_user  ->  {"rows":[{"u":"managed-mcp"}]}
select_query      HTTP 200   SELECT count(*) FROM mainline_audit.v_open_gate_summary
                             ->  {"rows":[{"n":1}]}   566 ms
```

The twelve tools: `create_database`, `create_table`, `explain_query`, `get_cluster`,
`get_table_schema`, `insert_rows`, `list_clusters`, `list_databases`, `list_tables`,
`select_query`, `show_running_queries`, `show_statement`.

**The argument names, settled from the server's own JSON Schema rather than from our reading of
prose.** This is the finding that matters.

```
select_query   required: ["database","query"]
   query        "The SQL query to execute (SELECT statements only). Use LIMIT/OFFSET in
                 your query for pagination."
   cluster_id   "Required when the MCP config has no cluster_id; otherwise must be omitted."
explain_query  required: ["database","query"]
insert_rows    required: ["database","query"]
   query        "The INSERT statement to execute. Include the full table name with optional
                 schema prefix …"
```

And the negative that pins it:

```
select_query {"database":"mainline_demo","statement":"SELECT 1 AS one"}
   ->  {"code": 0, "message": "must contain exactly one statement"}
```

Three consequences, each of which a worker must carry:

1. `ToolDialect.statement` must become `query`. **Measured, not documented.**
2. `select_query` has **no `limit` argument at all** — pagination is `LIMIT`/`OFFSET` inside the
   statement. `ToolDialect.limit` is a fiction on the read verbs and must be recorded as such.
3. `insert_rows` takes **a full INSERT statement**, not `{table, rows}`. Our
   `insert_external_attestation` — whose whole design point is that *no parameter names a
   table* — cannot be expressed on the live surface without constructing SQL. See ruling **R4**:
   we do **not** do that this week.

**The cluster is the one in the transcript.** `7cfc9ee9-f9b4-413d-bcad-d81fca2c6c7e`,
`mainline-dev`, SERVERLESS/Basic, `aws-ap-southeast-1`, v26.2.5, state `CREATED`
(`evidence/ccloud/cluster-list.txt`).

**The credential exists on this machine** — `CC_API_KEY` in `.env`, 69 characters — and is
therefore re-runnable by us. It is **not publishable**; see **R5**.

---

## 2. What the Official Rules actually require, cited

From the hackathon rules page (fetched 2026-08-16):

- **Five equally weighted Stage-Two criteria, in this order:** (1) **Agentic Memory Design** —
  *does CockroachDB function meaningfully as the agent's memory layer?*; (2) Technological
  Implementation; (3) Real-World Impact; (4) Product Readiness; (5) Creativity & Originality.
- **The tie-break is lexicographic:** *"if two or more Submissions are tied, the tied Submission
  with the highest score in the first applicable criterion listed above will be considered the
  higher scoring Submission,"* repeating through the remaining criteria in order.
- **At least 2 of 4 CockroachDB tools.** The four: **CockroachDB Cloud Managed MCP Server**,
  Distributed Vector Indexing, ccloud CLI (Agent-Ready), Agent Skills Repo (Open Source).
- **At least 1 AWS service.**
- **Functionality:** the project must function *"as depicted in the video and/or expressed in the
  text description."*

Source: <https://cockroachdb-ai.devpost.com/rules> · <https://cockroachdb-ai.devpost.com/>

**Read that against our position.** We already clear the ≥2 threshold three times over. The
Managed MCP row is therefore **not** worth points as a checkbox — it is worth points as
*criterion 1 evidence*, because it is the only one of the four tools where a stranger's agent
talks to our memory layer through a surface we did not write. That is the difference between
"we used the tool" and "the memory layer is agent-addressable", and criterion 1 is the one that
decides ties. **Every hour in this plan goes to depth on that sentence.**

---

## 3. Rulings — where the brief left something open, and my authority for closing it

**R1 — The premise correction stands and propagates.** MCP was already demonstrated; this plan
makes it current, deep, correctly filed and repeatable. *Authority: my live probe of 2026-08-16
plus `evidence/deploy/judge-run.json`.* No worker may write, in any document or commit message,
that the Managed MCP Server was previously undemonstrated. Equally, no worker may **delete or
relocate** `evidence/deploy/judge-run.json` or `evidence/deploy/judge-access.json`: they are
cited by `docs/TOOL-USAGE.md`, `docs/demo/ON-SCREEN-CLAIMS.md` and `MCP-CONFIG.md`, and
`evidence/mcp/` is **additive**.

**R2 — Reachability is PROVEN, and the plan says so with numbers, not adjectives.** The §1
measurements are the canonical statement. Any worker restating them must restate them exactly.

**R3 — The dialect correction is the highest-value change in this plan and is authorised.**
*Authority: the server's own `tools/list` inputSchema, which is a stronger source than either our
prose reading or CockroachDB's published documentation.* The correction must be **framed as the
design working**, not as a bug being hidden: `ToolDialect` existed precisely so this would be one
edit. Keep the previous names available as a second, named dialect constant with a comment saying
what they were and why they were wrong, so the repository does not quietly erase the guess it
published.

**R4 — No live write, and no rewrite of the write method. This is a hard stop.** `insert_rows`
is present on the live tool list and its measured shape is `{database, query}` — a full INSERT
statement. Making `insert_external_attestation` speak that shape means constructing SQL inside
the one method whose entire published guarantee is that *"insert into something else is not a
call the supported API can express."* We do not trade that guarantee for a demo on submission
eve. **No worker calls `insert_rows`, `create_database` or `create_table` against the live
cluster. No worker changes `insert_external_attestation`'s signature.** The measured live shape
is recorded as a **documented divergence** in `evidence/mcp/tools-schema.json` and in the package
README, phrased as: *the write verb's live argument shape differs from our typed one; the typed
one is not sent, because the surface it protects is worth more than the call.* *Authority: the
founder's standing prohibition on widening the write surface of this system without his call,
extended by me to "do not restructure the write surface at all this week."*

**R5 — "Repeatable by a judge" is defined here, because the honest answer is not the obvious
one.** The MCP credential is an **account-level Cloud service-account key**. Today's `tools/list`
reconfirms why it cannot be published: it carries `create_database`, `create_table` and
`insert_rows`, and `list_clusters` enumerates every cluster the account owns.
`evidence/deploy/judge-access.json` already records `credential_publishable: false`. Therefore
**repeatability has three legs and no fourth**:

  (a) a **committed transcript** a judge reads without any credential — `evidence/mcp/`;
  (b) a **one-command script** a judge runs against **their own** cluster with **their own** key,
      which reproduces the *mechanism* (handshake, twelve tools, schema blocklist, the audit-view
      shape) but not our data;
  (c) **Path B unchanged** — the read-only `mainline_judge` pgwire login, which is how a judge
      reads *our* ledger, already published and already verified from the other side.

**No document, script, caption or film line may imply that a judge can read MAINLINE's ledger
over MCP with a credential we hand them.** That is the single most tempting false claim in this
whole area and it is forbidden. *Authority: the founder's no-false-claim rule; the measured
tool list; `judge-access.json`.*

**R6 — The question worth asking is the audit-view interrogation, not `SELECT 1`.** The
demonstration this plan is graded on is: *a general-counsel question, routed deterministically to
a contracted `mainline_audit` view, answered over CockroachDB's own MCP endpoint, with its
completeness stated — and with none of MAINLINE's code in the read path.* Concretely the three
that matter: **what is the gate refusing right now** (`v_open_gate_summary`), **which weakenings
over severe blame ancestry were never answered for** (`v_weakenings_without_disposition`,
carrying `ancestry_complete`), and **was the vector index actually traversed** (`explain_query`).
Store → retrieve → act, over a surface we did not write. *Authority: the brief, plus criterion 1.*

**R7 — The N01 gap stays open and stays stated.** `mainline_qa.v_disposition_profile` **is**
readable by the `managed-mcp` identity; `GRANTS.yaml` S14 and the pack envelope both assert it is
not. That is a real gap, recorded as one. **No worker closes it by revoking a grant on submission
eve, and no worker deletes the divergence to make a suite go green.** A negative suite that has
quietly gone green is the worst artefact in the repository because it reads as the strongest.
*Authority: the founder's never-widen-a-grant rule, which I read as symmetrical — do not
restructure grants under deadline pressure in either direction — plus `docs/HONESTY.md`.*

**R8 — Ratchet direction.** Baseline is **1070 collected / 1069 passed / 0 failed / 0 errors**.
Collected may go **up**; passed may go **up**; **failed and errors stay 0**; every skip carries a
reason. In the credential-less pass every new live test must skip **with a reason**, never pass
vacuously. `DEFAULT_MAX_RESPONSE_BYTES == 136 * 1024` does not move. The console bundle guard
does not move. `continue-on-error` and `|| true` remain banned.

**R9 — `limits.py` is append-only above line 45.** `evidence/tool-usage/crdb-features.json`
anchors `crdb_managed_mcp` at `packages/mainline-mcp/src/mainline_mcp/limits.py:45` and records
`anchor_resolved.resolves: true`. Inserting lines above 45 silently breaks a published citation.
New constants go **below** the existing block; if any line above 45 moves, worker **M5** must
regenerate `crdb-features.json` and say so.

**R10 — The film beat may be upgraded only if the transcript lands.** `s19-beat5-mcp-connect`
reads *"Declared, not run here."* It may become a recorded live session **only** once M2 and M3
have committed a same-day transcript; otherwise the VO and the fallback stay exactly as they are.
*Authority: the Functionality rule — the project must function as depicted in the video.*

**R11 — Credential hygiene.** `CC_API_KEY` is present in `.env`. No worker prints it, echoes it,
logs it, or writes it into any artefact. Every new artefact under `evidence/mcp/` must carry the
same self-scan block `judge-run.json` carries (`credential_hygiene`: assertion, method,
`bytes_scanned`, `matches: 0`, `holds: true`) and must fail its own writer if a match is found.

**R12 — No deploy, no AWS, no commit.** No `terraform apply`, no redeploy, no AWS API call, no
SSM read or write. The only outbound network permitted is HTTPS **read verbs** to
`cockroachlabs.cloud/mcp` and GET/POST to the already-live Lambda origin. Leave the tree
uncommitted for the orchestrator.

---

## 4. The shape of the outcome, if all six land

A judge opening `evidence/mcp/README.md` sees, in one page: a handshake against CockroachDB's own
managed endpoint dated the day of submission; the twelve tools with their real JSON Schemas; the
sixteen-question pack driven **through the pack's own validator** rather than an ad-hoc client;
a general-counsel auditor asking nine questions of nine contracted views and stating the
completeness of every answer; a byte-budget prober proving each view fits in 80 % of the server's
truncation cap; three schema-blocklist refusals quoted verbatim from the server; and one honest
FAIL that nobody rounded off. Then a script they can run against their own cluster, and a plain
sentence about why our key is not the one we hand out.

That is criterion 1 answered with a transcript instead of an adjective.

---

## 5. The six workers — disjoint, literally enumerated

| id | title | owns (literal paths) |
|---|---|---|
| **M1** | Live dialect truth | `packages/mainline-mcp/src/mainline_mcp/client.py`, `packages/mainline-mcp/src/mainline_mcp/limits.py`, `packages/mainline-mcp/src/mainline_mcp/__init__.py`, `packages/mainline-mcp/tests/test_client.py`, `packages/mainline-mcp/README.md` |
| **M2** | Fresh live capture, correctly filed | `scripts/submission/capture_mcp_evidence.py`, `evidence/mcp/README.md`, `evidence/mcp/session.json`, `evidence/mcp/tools-schema.json`, `evidence/mcp/pack-run.json`, `verticals/mainline/demo/judge/runner.py` |
| **M3** | The agentic-memory interrogation, live | `packages/mainline-mcp/src/mainline_mcp/auditor.py`, `packages/mainline-mcp/src/mainline_mcp/budget.py`, `packages/mainline-mcp/src/mainline_mcp/catalogue.py`, `packages/mainline-mcp/tests/test_auditor.py`, `packages/mainline-mcp/tests/test_budget.py`, `evidence/mcp/auditor-live.json`, `evidence/mcp/budget-live.json` |
| **M4** | Close the never-ran-suites gap | `tests/integration/mcp/test_audit_surface.py`, `tests/integration/mcp/test_negative_reachability.py`, `tests/integration/mcp/test_live_dialect.py`, `qa/mcp-live.json` |
| **M5** | Documentation truth + judge repeatability | `docs/TOOL-USAGE.md`, `verticals/mainline/demo/judge/MCP-CONFIG.md`, `docs/deploy/JUDGE-PACK.md`, `evidence/tool-usage/crdb-features.json` |
| **M6** | Submission and film claim audit | `docs/submission/DEVPOST.md`, `docs/submission/VIDEO-KIT.md`, `docs/demo/ON-SCREEN-CLAIMS.md`, `docs/submission/RULES-MATRIX.md`, `docs/submission/SUBMISSION.json` |

**Not owned by anyone, and therefore not to be edited:** `verticals/mainline/demo/judge/QUESTIONS.yaml`,
`envelope.py`, `drift.py`, `pack.py`, `cli.py`, `scripts/deploy/judge_access.py`,
`evidence/deploy/*`, every migration, `docs/HONESTY.md`, `docs/ci/CI-STATE.md`.

**Ordering.** M1 first — M2, M3 and M4 all dial through it. M2 and M3 may run in parallel once
M1 lands. M5 needs M2's artefact paths. M6 needs M2, M3 and M5. M4 is independent of M5/M6.

**Every worker carries these three, verbatim, in its own brief:** no false claim; no regression
(1070/1069/0/0, skips carry reasons, ratchets only tighten); no deploy (no terraform, no AWS, no
SSM, no commit, no credential printed).
