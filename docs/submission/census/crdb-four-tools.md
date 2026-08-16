<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# CENSUS W3 — the four contest-named CockroachDB tools

**Worker:** W3 · **Date:** 2026-08-16 · **Plan:** [`docs/submission/feature-census-plan.md`](../feature-census-plan.md) · **Tree measured:** `c951558`

> **A note on the head, because this file's whole argument is that numbers get re-derived.** The
> plan and the brief both say `HEAD 5f57146`. Measured here today, `git rev-parse --short HEAD`
> returns **`c951558`** (*"docs(film): close the three film blockers…"*). Nothing in this file
> depends on which of the two it is — every claim below is anchored to a committed artefact, not
> to a commit id — but a census that quoted a head it had not looked at would be the exact failure
> it exists to prevent.

The Official Rules name four CockroachDB tools and require **at least two**. This file is the
compliance spine: one row per named tool, each with a state, an evidence path, a verification a
stranger can paste in under a minute **with that verification's real output**, and the exact
sentence the close block may use.

**Headline: four are named, three are exercised with a committed transcript, and the fourth is
shipped and not evidenced — which, against a floor of two, is a margin stated rather than a count
inflated.** Two of the three carry a live transcript against CockroachDB Cloud, one carries a
server-enforced refusal, and the fourth ships as installable open source with no run captured. The
`state` column is the plan's §R2 vocabulary; the `verdict` column is
`evidence/tool-usage/crdb-features.json`'s, and it is the word the film's closing card prints.

| # | contest-named tool | state | verdict | the one-line reading | the honest limit, stated in the row |
|---|---|---|---|---|---|
| 1 | **CockroachDB Cloud Managed MCP Server** | **REPO** | **EXERCISED** | Two committed end-to-end transcripts against `https://cockroachlabs.cloud/mcp`, five days apart. **15 of 16** both times. | verdict `DIVERGED — KNOWN GAP`; `credential_publishable: false` |
| 2 | **CockroachDB Distributed Vector Indexing** | **REPO** | **EXERCISED** | 3 `cspann` indexes, live in the same database the demo reads; the prefix rule is enforced by the server at `42809`. | no ANN query runs in the demo's HTTP request path |
| 3 | **ccloud CLI (Agent-Ready)** | **REPO** | **EXERCISED** | `ccloud auth whoami` + `ccloud cluster list -o json`, verbatim transcript, JSON parsed not screen-scraped. | 0.6.12 has no headless service-account auth — an agent cannot drive it cold |
| 4 | **CockroachDB Agent Skills Repo (Open Source)** | **DESIGNED** | **DESIGNED** | 3 skills validate under two validators; both authored scripts run locally and both can be made to fail. | **no run of either is captured under `evidence/`** — shipped and not evidenced; the upstream contribution is **staged, not filed**; the green CI run is at `2dc5c86`, behind the tip |

**Rows 1–3 are REPO, and that is the honest answer for them.** Under §R2, REPO means *exercised in
this repository, with a committed artefact, but not in the live demo's HTTP request path*. The live
origin's request path opens a `psycopg` connection and reads SSM; it does not call MCP, does not run
an ANN query, does not shell out to `ccloud`, and does not load a skill. Saying so is the
construction the repository already uses for Bedrock (§R4), and it costs nothing — because what
those three *do* carry is a transcript against the real managed cluster, which is a stronger
artefact than a code path a judge cannot see.

**Row 4 is not REPO and must never be written as REPO.** REPO's first clause is *a committed
artefact*, and there is none: no run of `assert_gate_refuses.py` or `assert_prefix_index_used.py` is
captured under `evidence/`. An earlier draft of this file ruled row 4 up to REPO on the strength of
a CI lane; **§4.1 now records that ruling as withdrawn.** The floor is two and three are exercised,
so the promotion bought nothing and risked the only thing this census sells.

---

## 0.1 · THE FOUR LINES THE CLOSING CARD PRINTS, AND THE FOUR COMMANDS THAT CHECK THEM

The film's closing card `k3` carries a four-row tools panel. **Every value on it is measured, and
every value resolves to a section of this file.** Nothing is on that card that is not below, and no
row on the card is in a better state than its row here.

| the panel row | verdict | the measured values on it | evidence path | §  |
|---|---|---|---|---|
| Distributed Vector Indexing (C-SPANN) | **EXERCISED** | **3** `cspann` indexes · **4** `VECTOR` columns · `42809` | `evidence/aws/ann/` | §2 |
| Managed MCP Server | **EXERCISED** | **15 of 16** · `DIVERGED — KNOWN GAP` · published, not rounded | `evidence/mcp/` | §1 |
| CockroachDB Cloud + `ccloud` CLI | **EXERCISED** | `cluster list -o json`, parsed not screen-scraped | `evidence/ccloud/` | §3 |
| CockroachDB Agent Skills | **DESIGNED** | shipped, validated; **NO RUN IS COMMITTED** | `skills/` | §4 |

Measured on 2026-08-16 for the first row, against the pinned local node: **3** indexes whose
`indexdef` contains `cspann`, and **4** columns of SQL type `vector` (plus one `tsvector`, which is
not counted as a vector column — see §2.1). `42809` occurs **3 times** in
`evidence/aws/ann/explain-unhinted.txt`: once in the file's own prose at `:26`, and **twice as the
refusal itself**, at `:205` and `:220`.

### 0.1.1 · The four one-liners, and the first line each one actually printed

**These four were run verbatim from the repository root on 2026-08-16 before being published here,
so nothing in this block is a command that has not been executed.** All four read committed files —
**no network call, no credential, and no cluster is needed for any of them**, which is why they are
the four the card prints. `python` is the repository interpreter, `.venv/Scripts/python.exe`.

```bash
# Managed MCP
python -c "import json;d=json.load(open('evidence/mcp/pack-run.json'));print(d['passed'],'/',d['total'],d['verdict'])"

# C-SPANN
grep -n "REFUSED BY THE SERVER" evidence/aws/ann/explain-unhinted.txt

# ccloud — the transcript, parsed rather than screen-scraped
tail -n +2 evidence/ccloud/cluster-list.txt | python -c "import json,sys;print([c['cockroach_version'] for c in json.load(sys.stdin)])"

# Agent Skills
python -c "import json;print(json.load(open('evidence/tool-usage/crdb-features.json'))['rows']['crdb_agent_skills']['verdict'])"
```

Observed output, pasted:

```
15 / 16 DIVERGED — KNOWN GAP

205:  REFUSED BY THE SERVER — SQLSTATE 42809
220:  REFUSED BY THE SERVER — SQLSTATE 42809

['v26.2.5']

DESIGNED
```

**The fourth command prints `DESIGNED`, and the card already said so** — which is the whole reason
the state is on the card. A judge who runs the four in the order the card lists them gets three
transcripts and one honest absence, and never has to take a sentence on trust.

### 0.1.2 · Two taxonomies are in play, and they must not be added together

`DEVPOST.md` already makes this point and this file repeats it, because the count is the thing a
rival team would attack first. **The hackathon's four named tools and this census's four `kind:
tool` rows are deliberately not the same four.**

* *The hackathon's* four: Distributed Vector Indexing, Managed MCP Server, `ccloud` CLI — in the
  order the Technological Implementation criterion enumerates them — then Agent Skills, which is
  named in the submission requirements and **not** in that criterion.
* *The census's* `kind` column splits its 14 CockroachDB rows **4 tools / 10 engine features**
  (`totals.by_kind`, measured in `evidence/tool-usage/crdb-features.json`). Its four tool rows are
  the database itself, Cloud with `ccloud`, the Managed MCP Server, and Agent Skills.

**So Distributed Vector Indexing appears above as one of the hackathon's four tools and is filed by
the census as one of its ten engine features — `crdb_vector_index`, `kind: feature`. That is one
thing counted under two schemes, not two things.** It is said out loud here so that nobody adds the
lists together and reports five, and because counting a feature as a tool to clear a bar is exactly
the arithmetic this repository exists to refuse.

---

## 1 · CockroachDB Cloud Managed MCP Server

```
state:        REPO  (EXERCISED, no live-origin check — §R2)
what it is:   CockroachDB Cloud's own hosted MCP endpoint, driven over Streamable HTTP with a
              service-account bearer key and an `mcp-cluster-id` header pinning one cluster.
where:        evidence/mcp/                          (session.json · tools-schema.json · pack-run.json · README.md)
              evidence/deploy/judge-run.json         → channels.mcp        (the first transcript, 2026-08-11)
              evidence/deploy/judge-access.json      → mcp_channel
              packages/mainline-mcp/src/mainline_mcp/limits.py:45   MCP_ENDPOINT
              docs/deploy/JUDGE-PACK.md §4           "available, working, and deliberately not published"
```

### 1.1 · The correction this row exists to make (plan §R1)

**The premise that the Managed MCP Server is undemonstrated is wrong, and it was wrong before this
census started.** It came from checking for a *directory* named `evidence/mcp/` and reading its
absence as an absence of evidence. The evidence was in `evidence/deploy/judge-run.json` the whole
time.

**And the directory now exists too.** Measured today: `evidence/mcp/` was written
**2026-08-16T07:33:26Z** and holds six files. So this row is not one transcript but **two,
independent, five days apart, agreeing on the number that matters**:

| | `evidence/deploy/judge-run.json` | `evidence/mcp/pack-run.json` |
|---|---|---|
| captured | 2026-08-11T00:23:29Z | 2026-08-16T07:33:46Z |
| driven by | an ad-hoc client inside `scripts/deploy/judge_access.py` | the pack's own runner, `verticals/mainline/demo/judge/runner.py::run_via_mcp` |
| result | **15 / 16** | **15 / 16** |
| verdict | `DIVERGED — KNOWN GAP` | `DIVERGED — KNOWN GAP` |
| the one failure | `N01` | `N01` |

The second run is the stronger artefact, and its README says why in its own words: the first ran
through a short ad-hoc client that carries none of the runner's three checks — the **envelope
validator** (refuses a statement that would breach a documented Managed-MCP limit *before* it is
transmitted), the **drift check** (binds each `EXPLAIN` to a vector literal of the dimension the
real migrations declare), and the **truncation guard** (flags a result of exactly 25 rows as
possibly truncated rather than reporting a page as the whole answer). The 2026-08-11 transcript is
*not* superseded — `evidence/mcp/README.md` says so explicitly, and both are cited here.

**I did not run a new MCP session and I touched no cloud credential.** Every number in this row was
read out of a committed file.

### 1.2 · What the endpoint returned

From `evidence/mcp/session.json`, verbatim:

```
initialize        HTTP 200   305.3 ms   protocolVersion 2025-06-18
                             serverInfo {"name": "cockroachdb-cloud", "version": "1.0.0"}
tools/list        HTTP 200   236.7 ms   12 tools, full JSON Schemas recorded
select_query      600.8 ms   sql_identity  ->  {"sql_identity": "managed-mcp", "bound_database": "mainline_demo"}
select_query      576.8 ms   audit_view_reachable  ->  {"n": 1}
```

Cluster `7cfc9ee9-f9b4-413d-bcad-d81fca2c6c7e` (`mainline-dev`), database `mainline_demo`. The key
resolves to the SQL login **`managed-mcp`** — not `root`, not the database owner. The twelve tools:
`create_database`, `create_table`, `explain_query`, `get_cluster`, `get_table_schema`,
`insert_rows`, `list_clusters`, `list_databases`, `list_tables`, `select_query`,
`show_running_queries`, `show_statement`.

The pack's own stdout, committed verbatim at `pack-run.json` → `cli_run.stdout` (exit `1`), ends:

```
  ANSWERED   Q10  bytes=1030  plan contains ['vector search', 'prefix spans']
  ANSWERED   Q10C bytes=906   plan contains ['vector search', 'prefix spans']
  ERROR      N01  rows=1  bytes=123  THE SERVER ANSWERED. This statement must fail; that it did
                                     not is the most serious result this pack can produce.
  REFUSED    N02  server refused: query references a restricted schema: access to "crdb_internal"
                                  is blocked for security reasons
  REFUSED    N03  server refused: ... "pg_catalog" ...
  REFUSED    N04  server refused: ... "information_schema" ...

12 answered, 3 refused, 0 skipped, 1 errors
```

**Read `Q10` and `Q10C` twice.** Those two are `EXPLAIN`s that came back as real query plans
carrying a `vector search` node and non-empty `prefix spans` — *tool 1 proving tool 2*, asked over
CockroachDB's own managed endpoint with none of our code between the question and the answer.

### 1.3 · The failure, carried at full weight

**`N01` fails, and it fails in both runs.** `N01` asserts that an MCP identity cannot read
per-person deliberation measurement. Measured, `managed-mcp` runs
`SELECT count(*) FROM mainline_qa.v_disposition_profile` successfully. `GRANTS.yaml` S14 and the
pack's own envelope both assert that is impossible. It is not.

Three facts travel with it, and none may be dropped:

1. **The run's own verdict is `DIVERGED — KNOWN GAP`,** and the pack exits `1`.
2. **`managed_mcp_availability.credential_publishable` is `false`.** The credential that reaches
   this endpoint is an account-level Cloud service-account key, its own tool list carries
   `create_database` / `create_table` / `insert_rows`, and `list_clusters` enumerates every cluster
   the account owns. It is not handed to anonymous judges, and this repository does not publish it.
3. **The published credential refuses what MCP allowed.** The read-only `mainline_judge` pgwire
   login refuses the same statement at SQLSTATE `42501` (no `USAGE` on `mainline_qa`) — measured in
   the same file under `divergences`. The credential a judge is actually given is the tighter of
   the two. That does not convert `N01` into a pass and it is not scored as one.

Closing the gap means revoking a grant on submission eve. Per the standing prohibition, **the grant
is not widened or narrowed by this census** — it is escalated in §5.

Two further honesty facts, both measured: this capture called **0** of the three write verbs, and
the prohibition is executed rather than promised — an `httpx` request hook parses every outgoing
JSON-RPC body and raises `WriteVerbAttempted` before transmission (`session.json` →
`read_only.enforced_how`). And with no key present, `.github/workflows/judge-pack.yml` requires
`run --via mcp` to exit **3 (NOT RUN)**, never 0, because *"a green negative run with nothing to
talk to asserts the opposite of what it claims."*

### 1.4 · Verify in 60 seconds — real output, pasted

```bash
python -c "import json;d=json.load(open('evidence/mcp/pack-run.json'));print(d['generated_at'],d['passed'],'/',d['total'],d['verdict'])"
python -c "import json;d=json.load(open('evidence/mcp/session.json'));print(d['identity']['sql_identity'],d['handshake']['server_info'],d['tool_count'],d['credential']['publishable'])"
python -c "import json;d=json.load(open('evidence/deploy/judge-run.json'));m=d['channels']['mcp'];print(m['endpoint'],m['ran'],m['passed'],'/',m['total'],d['verdict'],d['managed_mcp_availability']['credential_publishable'])"
```

Run on 2026-08-16 against this tree, these printed:

```
2026-08-16T07:33:46Z 15 / 16 DIVERGED — KNOWN GAP
managed-mcp {'name': 'cockroachdb-cloud', 'version': '1.0.0'} 12 False
https://cockroachlabs.cloud/mcp True 15 / 16 DIVERGED — KNOWN GAP False
```

Three lines, no credential, no network. The first is the fresh transcript, the second is the
identity and the publishability flag, the third is the independent 2026-08-11 run agreeing.

```
say this:     "We drove CockroachDB Cloud's Managed MCP Server end to end against our live cluster —
              protocol 2025-06-18, server cockroachdb-cloud 1.0.0, twelve tools — and ran a sixteen-
              question pack through it. Fifteen of sixteen. The one that failed is recorded, not
              rounded off: the MCP identity can read a schema our pack asserted it could not. And we
              do not publish that key, because its own tool list can create a database."

never say:    "Judges can query our ledger over MCP."  (`credential_publishable` is false — judges
              get the read-only `mainline_judge` pgwire login instead.)
              "The MCP pack passes."  (It exits 1. It is 15 of 16, verdict DIVERGED — KNOWN GAP.)
              "Our MCP integration is read-only."  (The *endpoint* is not. Our *client* is, and the
              enforcement is a request hook — say that instead.)
```

---

## 2 · CockroachDB Distributed Vector Indexing

```
state:        REPO  (EXERCISED, no live-origin check — §R2)
what it is:   C-SPANN distributed vector indexes over 1024-dimension embeddings, each with
              mandatory prefix columns that select which K-means tree is searched.
where:        verticals/mainline/db/migrations/0031_clause_embedding.sql:149   VECTOR INDEX ce_ann …
              evidence/aws/ann/ann-proof.json · explain-hinted.txt · explain-unhinted.txt · the-one-query.sql
              skills/designing-vector-recall-prefixes/                         (the rule, written down)
              evidence/mcp/pack-run.json → results Q10, Q10C                   (the plan, over MCP)
```

### 2.1 · The R8 correction, applied

The brief's "5 live VECTOR columns" is imprecise. Measured today against the pinned local node,
`information_schema.columns`:

```
mainline.clause_embedding.embedding    vector
mainline.event_cue_coarse.emb_coarse   vector
mainline.event_cue_embedding.emb       vector
mainline.event_cue_stage.emb           vector
mainline.event_cue.tsv                 tsvector
```

**Four `vector` columns across four tables, plus one generated `tsvector`.** The corrected claim is
stronger than the wrong one, exactly as §R8 predicted: four dense-vector columns, **three C-SPANN
distributed vector indexes with mandatory prefix columns**, *and* a full-text `tsvector` in the same
schema — one database serving hybrid lexical + dense recall, with the gate that refuses the write
sitting in the same transaction domain. Note the fourth vector column, `event_cue_stage.emb`, is a
staging table and carries **no** `cspann` index; three of four are indexed, and saying "three
indexes over four vector columns" is both true and self-evidently counted.

### 2.2 · The three indexes, quoted from `pg_indexes`

```sql
CREATE INDEX ce_ann         ON mainline_demo.mainline.clause_embedding
                            USING cspann (site_id, activity_root, embedding vector_cosine_ops)
CREATE INDEX cue_scoped_idx ON mainline_demo.mainline.event_cue_embedding
                            USING cspann (site_id, scope_id, facet, emb vector_cosine_ops)
CREATE INDEX cue_sweep_idx  ON mainline_demo.mainline.event_cue_coarse
                            USING cspann (tenant_id, emb_coarse vector_cosine_ops)
```

Two prefix columns, three prefix columns, one prefix column. That spread is deliberate and it is the
interesting part.

### 2.3 · The prefix rule — the fact worth the close block

`skills/designing-vector-recall-prefixes/SKILL.md` states it as the rule that decides everything:

> **A vector index is used only if EACH prefix column is constrained to a specific value.**

And the consequence that makes it a *correctness* surface rather than a performance knob: C-SPANN
maintains **a separate K-means tree per distinct prefix value**, so a row written under the wrong
prefix "is in a different tree, so no constrained query will ever reach it — with no error and no
row anywhere that looks wrong."

**The server enforces it.** From `evidence/aws/ann/explain-unhinted.txt`, Appendix B — drop either
prefix column while keeping the index hint:

```
  REFUSED BY THE SERVER — SQLSTATE 42809
  index "ce_ann" cannot be used for this query

  Not a worse plan. A refused one. This is the prefix rule enforced by
  CockroachDB rather than asserted by a comment.
```

A refusal is a far better artefact than a benchmark, and it is the same shape as the rest of this
project: the database says no.

### 2.4 · The plan, and the counterfactual that did not reproduce

From `evidence/aws/ann/explain-hinted.txt` — 1,080 rows under one `site_id`, 1024 dimensions,
`amazon.titan-embed-text-v2:0`, captured 2026-08-11T04:07:47Z against `mainline-dev`:

```
└── • vector search
      table: clause_embedding@ce_ann
      target count: 10
      prefix spans: [/'5b144fe2-c64e-54a4-8b7c-2e3eb31497b6'/'/mill' - /'5b144fe2-c64e-54a4-8b7c-2e3eb31497b6'/'/mill']
```

**The unflattering half is captured on purpose and must travel with the row.** ADR 0002 GT-06
recorded that at ~5,200 rows the optimizer does *not* choose the vector index without a hint. That
did **not** reproduce: on this cluster the unhinted plan traverses `ce_ann` too, at every row count
swept (0 / 200 / 1,100 / 5,300). The artefact records `gt06_counterfactual_reproduces: false` in its
own caveat list rather than quietly dropping it. What still holds — and what the design actually
depends on — is the `42809` refusal above, which is a server property and not an optimizer mood.

Two further caveats from the artefact's own list, because they bound the recall numbers: **the
corpus is synthetic** (every report authored for this repository) and **latency here is not a
benchmark** (single issue per query, Windows workstation in Australia to Singapore, no interval).
Recall over 96 queries, grade ≥ 2, single-root arm: `28/96 = 0.292 [0.210, 0.389]` at k=1 and
`74/96 = 0.771 [0.677, 0.844]` at k=10, 95% Wilson.

### 2.5 · Verify in 60 seconds — real output, pasted

```bash
docker exec trappoint-crdb ./cockroach sql --insecure -d mainline_demo --format=csv \
  -e "SELECT indexname, indexdef FROM pg_indexes WHERE indexdef ILIKE '%cspann%' ORDER BY indexname;"
grep -n "prefix spans" evidence/aws/ann/explain-hinted.txt
```

Run on 2026-08-16, these printed:

```
indexname,indexdef
ce_ann,"CREATE INDEX ce_ann ON mainline_demo.mainline.clause_embedding USING cspann (site_id, activity_root, embedding vector_cosine_ops)"
cue_scoped_idx,"CREATE INDEX cue_scoped_idx ON mainline_demo.mainline.event_cue_embedding USING cspann (site_id, scope_id, facet, emb vector_cosine_ops)"
cue_sweep_idx,"CREATE INDEX cue_sweep_idx ON mainline_demo.mainline.event_cue_coarse USING cspann (tenant_id, emb_coarse vector_cosine_ops)"

67:              prefix spans: [/'5b144fe2-c64e-54a4-8b7c-2e3eb31497b6'/'/mill' - /'5b144fe2-c64e-54a4-8b7c-2e3eb31497b6'/'/mill']
```

A judge with no Docker can reach the same fact over the network instead: `Q10` and `Q10C` in
`evidence/mcp/pack-run.json` are `EXPLAIN`s taken over the Managed MCP Server against the **cloud**
`mainline_demo`, and both came back carrying `vector search` and `prefix spans`. The indexes are not
merely in a migration file — they are in the database the live demo reads.

```
say this:     "Recall is a C-SPANN distributed vector index inside the same database that holds the
              gate, so retrieval and refusal share one transaction domain. Three vector indexes over
              four VECTOR columns, plus a generated tsvector for full-text in the same schema. Every
              prefix column must be bound to a single value or CockroachDB refuses the query outright
              — SQLSTATE 42809 — and we ship that refusal as evidence, not as a comment."

never say:    "The demo does an ANN search when you click it."  (No ANN query runs in the demo's HTTP
              request path. The indexes are live in the database; the search is evidenced in
              evidence/aws/ann/ and over MCP.)
              "5 vector columns."  (Four. The fifth is a tsvector — and saying so is the better claim.)
              "The optimizer needs our hint."  (It did not reproduce. The 42809 prefix refusal is the
              claim that survived.)
```

---

## 3 · ccloud CLI (Agent-Ready)

```
state:        REPO  (EXERCISED, no live-origin check — §R2)
what it is:   CockroachDB Cloud's first-party CLI, driven with `-o json` so its output is parsed
              rather than screen-scraped.
where:        evidence/ccloud/cluster-list.txt   (verbatim transcript, ANSI spinner frames stripped)
              evidence/ccloud/README.md:37       (the measured limitation)
```

The transcript is `ccloud auth whoami` followed by `ccloud cluster list -o json`, captured
2026-08-10, and it establishes the cluster every other row in this file points at: `mainline-dev`,
`v26.2.5`, `SERVERLESS` on AWS `ap-southeast-1`, id `7cfc9ee9-f9b4-413d-bcad-d81fca2c6c7e`, with
`spend_limit: 2500` — the US$25.00 monthly cap set at cluster creation.

**The `-o json` flag is the whole point of the "agent-ready" claim**, and it is the reason the file
can be verified with a JSON parser rather than a human eye.

**The limitation is measured and is stated wherever the tool is named.** `ccloud` **0.6.12** is the
latest published build (0.7.0 / 0.8.0 / 0.9.0 / 1.0.0 all 404 from `binaries.cockroachdb.com`) and
it has **no non-interactive service-account authentication**: `ccloud auth` exposes only
`login` / `logout` / `whoami`, `login` is browser-based, and `CC_API_KEY` in the environment is
ignored. **Therefore an agent cannot drive `ccloud` headlessly from a cold start, and this project
does not claim that it does.** Headless paths use the Cloud REST API with the same service-account
credential — verified live against `/clusters`, `/clusters/{id}`, `/service-accounts`, `/api-keys`
and `/clusters/{id}/sql-users`. A second measured absence: audit-log endpoints 404 on this tier, so
the "custody of the custodian" design has no input source here and is documented as unavailable
rather than shipped as an unbacked claim.

### 3.1 · Verify in 60 seconds — real output, pasted

```bash
python -c "
import json
t=open('evidence/ccloud/cluster-list.txt',encoding='utf-8').read()
print(t.splitlines()[0])
c=json.loads(t[t.index('['):])[0]
print(c['name'],c['cockroach_version'],c['plan'],c['cloud_provider'],c['regions'][0]['name'],c['id'])
"
```

Run on 2026-08-16, this printed:

```
logged in to "Not Applicable" (org-3bkz4) as Shaugato-AWS Paroi
mainline-dev v26.2.5 SERVERLESS AWS ap-southeast-1 7cfc9ee9-f9b4-413d-bcad-d81fca2c6c7e
```

That the second line *parses* is the claim: the transcript is machine-readable output, not a
screenshot. And the cluster id it prints is the same id `evidence/mcp/session.json` pins with the
`mcp-cluster-id` header — two named tools, independently captured, agreeing on one cluster.

```
say this:     "We use the ccloud CLI with -o json and parse it — the committed transcript is
              machine-readable, and the cluster id in it is the same one our MCP session pins.
              We also state the limit we hit: ccloud 0.6.12 has no non-interactive service-account
              auth, so headless paths use the Cloud REST API with the same key."

never say:    "Our agent drives ccloud."  (It cannot, from a cold start, on 0.6.12. Measured.)
              "ccloud runs in our CI."  (Nothing in this repository has ever run against
              CockroachDB Cloud in CI. The transcript is a human session.)
```

---

## 4 · CockroachDB Agent Skills Repo (Open Source)

```
state:        DESIGNED  (the generator's verdict, KEPT — see §4.1, where this file's earlier
                        promotion to REPO/EXERCISED is withdrawn. NO RUN IS CAPTURED UNDER
                        evidence/: the skills are shipped and not evidenced.)
what it is:   Agent Skills for building database-enforced refusals on CockroachDB, distributed
              two ways (Agent Skills spec + Claude Code plugin marketplace), each shipping a script
              that FAILS when the guarantee does not hold.
where:        skills/designing-diachronic-gates/          SKILL.md + 3 references + assert_gate_refuses.py
              skills/designing-vector-recall-prefixes/    SKILL.md + cspann-prefix-rules.md + assert_prefix_index_used.py
              skills/upstream/…/verifying-a-restore-by-merkle-root/   de-branded, STAGED, not filed
              skills/validate-spec.py                     our implementation of the published spec rules
              .github/workflows/skills.yml                three jobs, two of them red-half-first
              .claude-plugin/marketplace.json             the plugin distribution manifest
```

### 4.1 · The ruling, WITHDRAWN — this row stays DESIGNED

> **Amended 2026-08-16.** An earlier version of this section ruled that the census state for this
> tool was *REPO (= EXERCISED)* and that the generator was understated against its own definition.
> **That ruling is withdrawn.** The row's verdict is **DESIGNED**, the generator's own word, and it
> is the word the film's closing card prints. The argument that produced the promotion is preserved
> below, because it is a real argument and deleting it would hide why the state was ever in doubt —
> but it is preserved as an argument that was **not** acted on. Three reasons it was withdrawn are
> in §4.1.1, and the decisive one is the second.

`evidence/tool-usage/crdb-features.json` marks `crdb_agent_skills` **DESIGNED** with this basis:

> *"two skills are on disk, each shipping an executable assertion script; **neither script's run is
> captured under `evidence/`**, so they are shipped and not evidenced"*

The generator's own vocabulary, from the same file, is:

> **EXERCISED** — *"it ran, and a committed artefact **or a check in this repository** records the
> result"*

**The basis tests only the first clause of its own definition.** Measured today, the second clause
holds:

1. **`.github/workflows/skills.yml` is a check in this repository that runs both scripts**, and it
   runs the failing half first: five planted spec violations each refused *by name*, four planted
   marketplace violations each refused *by name*, the nine-row unwelding matrix against
   `cockroachdb/cockroach:v26.2.5` in Docker (four rows of which must end `ADMITTED`), and a
   red-before-green step that requires the same assertion to **exit 1** against an unwelded schema.
2. **That lane has run and it was green.** `docs/CI-STATE.md:242` records run
   [`31699588327`](https://github.com/Shaugato/mainline/actions/runs/31699588327), **success**, at
   commit `2dc5c86`, 2026-08-13T12:20:50Z, by dispatch.
3. **Both scripts run here, today, on a machine with no credential**, which is the property the
   skills actually sell.

**That was the case for promotion. It is not accepted.** Two caveats always travelled with it, and
on re-reading they are not caveats — they are the answer:

- **The green run is at `2dc5c86`, which `docs/CI-STATE.md` itself calls "five commits behind" the
  tip it was measuring.** A green whose head is old is a claim about a tree nobody is running. The
  cure is a dispatch, not a sentence — escalated in §5.
- **No `evidence/` JSON artefact of a skill-script run is committed.** The record is a CI run id plus
  a locally reproducible self-test. That is weaker than the MCP row's transcript, and neither the
  close block nor the film may imply otherwise.

#### 4.1.1 · Why the promotion was withdrawn, in order of weight

1. **Part 2 of the promotion's own detector refutes it.** The detector stores the commit beside the
   run id precisely so a stale green cannot masquerade as a green at HEAD — and the recorded green
   is stale. A predicate that is built to catch this exact failure, and then catches it, has
   answered the question.
2. **REPO's first clause is a committed artefact, and there is none.** *"Neither script's run is
   captured under `evidence/`"* is the generator's basis string, and this file has never been able
   to contradict it — it argued around it, via the definition's second clause. **On the one page a
   judge is pointed at for states, arguing around a missing artefact is the failure mode this whole
   census exists to prevent.** The correct verb for a shipped-and-unevidenced tool is *DESIGNED*.
3. **It bought nothing.** The eligibility floor is **two**; three tools carry a committed
   transcript. Promoting a fourth changes no outcome and puts the credibility of the other three in
   play. A `DESIGNED` sitting in the same column as three `EXERCISED`s is the reason a judge
   believes the three.

**The cure is a captured run, and capturing one is out of scope for this wave** — nothing under
`evidence/` or `skills/` is written by this file, and the state is reported here, never created.
The verdict moves when a run is committed, not when a sentence is rewritten. Per §R6 the detector
is still proposed as prose, not as an edit to the generator — see §6. **I did not touch
`scripts/submission/capture_tool_evidence.py`.**

### 4.2 · What is actually there

Three `SKILL.md` files, and the count is 2 + 1, not 3-of-a-kind:

| skill | it answers | it proves it with |
|---|---|---|
| `designing-diachronic-gates` | how do I make the database refuse a transition because of the subject's **history**, and how do I know it really refuses? | `assert_gate_refuses.py` — spins a throwaway node, replays an illegal history, fails unless the expected **SQLSTATE and constraint name** are raised, then unwelds the schema six ways to prove each mechanism is load-bearing |
| `designing-vector-recall-prefixes` | what should a C-SPANN index's prefix columns be, and how do I prove from `EXPLAIN` the index was used? | `assert_prefix_index_used.py` — asserts the plan fragment, including the full scan sitting beside a legitimate vector search |
| `skills/upstream/…/verifying-a-restore-by-merkle-root` | **not ours to ship** — a de-branded skill staged in another repository's directory shape, **ready to file and not filed** | `verify_restore_merkle_root.py --self-test`, standard library only |

The staging tree is deliberately **absent** from `.claude-plugin/marketplace.json` — the manifest
enumerates the two branded directories explicitly rather than globbing `./skills` — and the CI
marketplace checker plants that exact violation and requires a refusal by name.

### 4.3 · Verify in 60 seconds — real output, pasted

```bash
python skills/validate-spec.py skills/ --strict
python skills/designing-vector-recall-prefixes/scripts/assert_prefix_index_used.py --self-test
python skills/designing-diachronic-gates/scripts/assert_gate_refuses.py --parser-self-test
```

Run on 2026-08-16 against this tree, no database and no credential, these printed:

```
[OK] skills/designing-diachronic-gates
[OK] skills/designing-vector-recall-prefixes
[OK] skills/upstream/cockroachdb-resilience-and-disaster-recovery/verifying-a-restore-by-merkle-root

3 skill(s), 0 error(s), 0 warning(s)
```

```
[PASS] constrained vector search: accepted
[PASS] no vector search at all: ["no `vector search` node: the optimizer did not use a vector index. Node types present: ['scan', 'top-k']", 'the plan contains a FULL SCAN (scan)']
[PASS] prefix not constrained: ["prefix spans are '[]': at least one prefix column was NOT constrained to a specific value, so this query is not searching the partition it looks like it is"]
[PASS] full scan beside a real vector search: ['the plan contains a FULL SCAN (scan)']

self-test: OK
```

```
[PASS] check violation names its constraint: 23514 / gate_closed_when_issued
[PASS] fk violation names its constraint, past a DETAIL line: 23503 / completion_pin
[PASS] P0001 carries NO constraint line; the exhibit is parsed from the message: P0001 / fn_subject_close_gate (parsed)
[PASS] a P0001 that does not follow the message convention yields NO exhibit: P0001 / <no exhibit> (none)
[PASS] a clean run is reported as ADMITTED, not as a refusal
[PASS] an admission is a FAIL
[PASS] a wrong exhibit is a FAIL

parser self-test: OK
```

Note the last three lines of the third block: the parser self-test asserts that an **admission is a
FAIL** and a **wrong exhibit is a FAIL**. A skill whose script cannot go red is a blog post.

```
say this:     "We authored two CockroachDB Agent Skills and published them under Apache-2.0, through
              both the Agent Skills spec and a Claude Code plugin marketplace. Each ships a script
              that fails when the guarantee does not hold — and CI runs the failing half first: nine
              unwelding rows against a throwaway CockroachDB node, four of which must ADMIT, plus
              nine planted violations each refused by name. A third skill is de-branded and staged
              for contribution to cockroachlabs/cockroachdb-skills. We file this one DESIGNED, not
              exercised — no run of either script is captured under evidence/, so it is shipped and
              not evidenced. It is a fourth tool past a floor of two, and we do not promote it to
              lengthen a list."

never say:    "All four contest tools are exercised."  (Three are, each with a committed
              transcript. This one is DESIGNED, and the closing card prints DESIGNED in the same
              capitals it prints EXERCISED in.)
              "Our skill was merged upstream."  (Nothing is merged. The CI claims-grep fails the
              build on that sentence.)
              "We contributed a skill to CockroachDB."  (It is STAGED and READY TO FILE. Measured:
              docs/upstream/proposal-issue.md still says "Skill, ready to file" and carries a
              re-check list to run BEFORE filing. Claim the filing only once it is filed — and even
              then, the filing, never the merge.)
              "The skills CI is green at HEAD."  (The recorded green is at 2dc5c86, five commits
              behind the tip that measured it.)
              "The upstream repository is stalled."  (It is not. PR #18 merged 2026-07-22. The only
              permitted sentence is that two specific PRs have had no maintainer engagement.)
```

---

## 5 · Escalations — undecidable here, for the founder (§R7)

Nothing in this section was acted on. Each is out of scope by construction.

| # | the open question | why it is not mine |
|---|---|---|
| E1 | **`N01` / the `mainline_qa` grant.** The `managed-mcp` identity can read `mainline_qa.v_disposition_profile`; the pack asserts it cannot. Closing it means revoking a grant on submission eve. | Standing prohibition: **never widen or narrow a database grant.** And a negative suite that has quietly gone green is the worst artefact in a repository, because it reads as the strongest. |
| E2 | **Re-dispatch the `skills` lane at the tip.** The recorded green is at `2dc5c86`. A dispatch would convert "green five commits ago" into "green at HEAD" and costs one click. | Not mine to trigger; and CI state is W7/orchestrator territory. |
| E3 | **File the upstream proposal, or state clearly that it is staged.** `docs/upstream/proposal-issue.md` carries a four-item re-check list to run first (the target domain was `.gitkeep`-only on 2026-08-10 and that stops being true the moment somebody else files). | Filing is a public action on another organisation's repository. Founder's call. |
| E4 | **`crdb_agent_skills` reads DESIGNED, and this file now agrees with it.** The open question is not the verdict but the *basis string*, which tests only the first clause of the generator's own EXERCISED definition. **Nothing here asks for a promotion** — a promotion needs a captured run under `evidence/`, and capturing one is prohibited in this wave. | §R6: workers propose detectors; they do not edit the generator, and they do not manufacture the evidence that would move a verdict. Detector in §6. |

---

## 6 · Detectors, so §4.1 is re-derivable by the generator (§R6)

Proposed for `scripts/submission/capture_tool_evidence.py`, as prose plus the exact probe. **Not
applied by this worker.**

**`crdb_agent_skills` → the verdict stays `DESIGNED`; only the `verdict_basis` gets sharper.** The
proposal below is a two-part predicate, both parts machine-checkable. **Part 2 is what refuses the
promotion**, and it is included for exactly that reason — a detector that can only ever say yes is
not a detector:

```python
# part 1 — a check in this repository runs both shipped scripts (the generator's own
# EXERCISED definition says "or a check in this repository records the result")
workflow = Path(".github/workflows/skills.yml").read_text("utf-8")
runs_both = (
    "assert_gate_refuses.py" in workflow
    and "assert_prefix_index_used.py" in workflow
    and "--self-test --docker-only" in workflow          # the matrix, not just the parser
    and "must exit 1" in workflow                        # the red half
)

# part 2 — the lane has a recorded green, and the generator records WHICH TREE it was at,
# so a stale green can never masquerade as a green at HEAD
#   docs/CI-STATE.md row: `skills` | success | run 31699588327 | 2dc5c86 | 2026-08-13T12:20:50Z
```

Suggested `verdict_basis` text, carrying its own caveat the way `crdb_managed_mcp`'s does:

> DESIGNED, and the basis is sharpened rather than the verdict moved (2026-08-16).
> `.github/workflows/skills.yml`
> runs `assert_gate_refuses.py --self-test --docker-only` (nine unwelding rows against
> `cockroachdb/cockroach:v26.2.5`, four of which must ADMIT), `assert_prefix_index_used.py
> --self-test`, and a red-before-green step requiring exit 1 on an unwelded schema; plus five
> planted spec violations and four planted marketplace violations, each refused by name. Recorded
> green: run 31699588327, 2026-08-13T12:20:50Z, **at commit `2dc5c86`, not at the tip**. NOT
> CLAIMED: no `evidence/` artefact of a skill-script run is committed, and the upstream
> contribution is staged and **not filed**.

**A second, smaller detector — `crdb_managed_mcp`'s anchor.** The row currently anchors to
`packages/mainline-mcp/src/mainline_mcp/limits.py:45`, which is a constant. Now that
`evidence/mcp/` exists, a stronger anchor is available and is a one-field change:
`evidence/mcp/pack-run.json` with `must_contain: "DIVERGED"` — an anchor that resolves only while
the divergence is still honestly recorded.

---

## 7 · What this worker did not do

> **Amendment, 2026-08-16 (close-card wave, worker W5).** This section is kept as written and
> extended, not replaced. Since it was first published, this file has been amended three ways and
> **every amendment moves a claim down or leaves it flat — none moves one up.** §4/§4.1 withdraw
> the promotion of Agent Skills and restore **DESIGNED**; §0 adds the generator's `verdict` column
> beside the §R2 `state` column so the two vocabularies cannot silently diverge; §0.1 adds the four
> panel rows, the four one-liners **as actually run**, and the two-taxonomies note. Additional
> reads made for those: four verification one-liners run from the repository root, and two
> `SELECT`s against the pinned local node (`pg_indexes`, `information_schema.columns`) confirming
> **3** `cspann` indexes and **4** `vector` columns. **No file under `evidence/`, `skills/` or
> `infra/` was written or read for anything but text; no run was captured to promote a row; no
> commit.**

- **No new MCP session, and no cloud credential was read, written or printed.** Every MCP number
  here was parsed out of a committed file (§R1's explicit instruction).
- **No deploy, no `terraform apply`, no redeploy, no SSM write, no AWS API call.**
- **No grant widened or narrowed.** E1 stays open.
- **No commit.** One file written: `docs/submission/census/crdb-four-tools.md`.
- **No generator, ratchet or honesty document edited.** No `continue-on-error`, no `|| true`.
- **No regression is possible from this change**: it adds one Markdown file under
  `docs/submission/census/`, touches no code, no test, no fixture and no threshold. The baseline
  (1070 collected / 1069 passed / 0 failed / 0 errors), the gate proof verdict,
  `DEFAULT_MAX_RESPONSE_BYTES == 136 * 1024` and the console bundle-headroom guard are untouched by
  construction. The suite was not run, and this line says so rather than implying a run that did
  not happen.
- **Reads only** against the local cluster: two `SELECT`s over `pg_indexes` and
  `information_schema.columns` on `mainline_demo`. No scratch database was needed and none was
  created.

### 7.1 · This file was scanned by the hygiene ratchets before it was handed over

Both scanners were run today. `scripts/submission/check_submission_prose.py` exits **0**
(`claim hygiene OK` / `submission prose OK`), and this file was additionally scanned **directly**,
which neither scanner's globs reach today — `claim_hygiene`'s surface is 23 named globs and the
submission surface is `docs/submission/*.md`, non-recursive:

```bash
python scripts/demo/claim_hygiene.py --check docs/submission/census/crdb-four-tools.md
```

Result, **re-run after the 2026-08-16 close-card amendment: 14 findings, every one of them
`HYG-sha-literal`, and zero findings in any other family** — including every must-not-claim rule.
(It was 10 before the amendment; the four new ones are further citations of the same stale-green
commit, added by §4.1.1 and by the `verdict` column, and the count is re-stated rather than left at
the number that was true yesterday.) `HYG-sha-literal` is the one family the submission surface
deliberately scopes out, in the scanner's own printed words: *"a provenance disclosure's job is to
quote git commits; the ban is on SHAs in the film and the deck, where `commit_id` cannot be chosen
in advance."* The literals here are `5f57146`, `c951558` and `2dc5c86` — the last of which is
load-bearing, because "the skills lane is green at `2dc5c86`, not at the tip" is not a checkable
sentence without it, and it is the sentence that now **holds this row at DESIGNED**.
`docs/CI-STATE.md` and the census plan itself quote commits the same way.
**W7: if the submission glob is ever widened to `docs/submission/**/*.md`, this file passes — that
family is not re-applied there.**
