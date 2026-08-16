<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0

GENERATED FILE — do not edit by hand.
Produced by scripts/submission/capture_mcp_evidence.py against the live endpoint.
-->

# CockroachDB Cloud Managed MCP Server — the transcript

**Captured 2026-08-16T07:33:26Z** against `https://cockroachlabs.cloud/mcp`, cluster `7cfc9ee9-f9b4-413d-bcad-d81fca2c6c7e` (`mainline-dev`), database `mainline_demo`.

This directory answers one question: *does an agent that is not ours reach MAINLINE's memory layer through a surface we did not write?* Everything below was measured on the date above, by `scripts/submission/capture_mcp_evidence.py`. Nothing here is a plan.

## The files this capture writes

| file | what it holds |
|---|---|
| `session.json` | the handshake — HTTP status, latency, the protocol revision the server named, its `serverInfo`, and the SQL identity our key resolves to |
| `tools-schema.json` | all 12 tools with their **full** `inputSchema`, and a divergence block derived from those schemas |
| `pack-run.json` | the sixteen-question judge pack driven through the pack's own runner, with per-question verdicts |
| `README.md` | this page |

Also in this directory, written by their own captures rather than by this one: `auditor-live.json`, `budget-live.json`. Each states its own provenance and its own scan in the `produced_by`, `generated_at` and `credential_hygiene` fields it carries; this page does not describe their contents, because a quotation of another program's output goes stale the next time that program runs.

## What was measured

```
initialize        HTTP 200   305.3 ms   protocolVersion 2025-06-18
                             serverInfo {"name": "cockroachdb-cloud", "version": "1.0.0"}
tools/list        HTTP 200   236.7 ms   12 tools, full JSON Schemas recorded
select_query      600.8 ms   sql_identity  ->  {"sql_identity": "managed-mcp", "bound_database": "mainline_demo"}
select_query      576.8 ms   audit_view_reachable  ->  {"n": 1}
```

The twelve tools: `create_database`, `create_table`, `explain_query`, `get_cluster`, `get_table_schema`, `insert_rows`, `list_clusters`, `list_databases`, `list_tables`, `select_query`, `show_running_queries`, `show_statement`.

The key resolves to the SQL login `managed-mcp`, bound to `mainline_demo`.

## The sixteen-question pack, through the pack's own runner

`python verticals/mainline/demo/judge/cli.py run --via mcp` → `verticals/mainline/demo/judge/runner.py::run_via_mcp`. **15 of 16**, exit `1` (checked and at least one question did not behave — see the results).

The same command was **also executed as a subprocess**, and the stdout a judge sees when they type it is committed verbatim at `pack-run.json` → `cli_run.stdout` (exit `1`). That is a second live run — 10.4 s, taken seconds before the structured one — and not a rendering of the table below, so the two agree on outcomes and need not agree to the millisecond.

This path had never reached the live surface until 2026-08-16, because the client it dials through sent the SQL under the argument name `statement` and the live schema requires `query` — every call came back *must contain exactly one statement*. The 2026-08-11 transcript in `evidence/deploy/judge-run.json` — which is real, is unchanged, and is not superseded as a record — was driven instead by a short ad-hoc client inside `scripts/deploy/judge_access.py`, which carries none of the runner's three checks:

- the **envelope validator**, which refuses a statement that would breach a documented Managed-MCP limit *before* it is transmitted;
- the **drift check**, which binds each `EXPLAIN` to a vector literal of the dimension the real migrations declare, so a plan proof cannot pass against a stale dimension;
- the **truncation guard**, which flags any result of exactly 25 rows as possibly truncated rather than reporting the page as the whole answer.

| question | outcome | expected | verdict | rows | bytes | ms |
|---|---|---|---|---|---|---|
| `Q01` | answered | answered | **PASS** | 1 | 425 | 1178.6 |
| `Q02` | answered | answered | **PASS** | 0 | 109 | 596.8 |
| `Q03` | answered | answered | **PASS** | 1 | 462 | 584.0 |
| `Q04` | answered | answered | **PASS** | 1 | 349 | 600.5 |
| `Q05` | answered | answered | **PASS** | 0 | 109 | 616.6 |
| `Q05F` | answered | answered | **PASS** | 0 | 109 | 584.3 |
| `Q06` | answered | answered | **PASS** | 1 | 470 | 583.3 |
| `Q07` | answered | answered | **PASS** | 1 | 507 | 614.7 |
| `Q08` | answered | answered | **PASS** | 0 | 110 | 565.7 |
| `Q09` | answered | answered | **PASS** | 0 | 110 | 580.7 |
| `Q10` | answered | answered | **PASS** | — | 1030 | 613.0 |
| `Q10C` | answered | answered | **PASS** | — | 906 | 673.5 |
| `N01` | error | refused | **FAIL** | 1 | 123 | 594.6 |
| `N02` | refused | refused | **PASS** | — | — | — |
| `N03` | refused | refused | **PASS** | — | — | — |
| `N04` | refused | refused | **PASS** | — | — | — |

### The one that failed — `N01`

mainline_qa IS readable by the Managed MCP identity. N01 claims an MCP identity cannot read per-person deliberation measurement; measured, it runs successfully. GRANTS.yaml S14 and the pack envelope both assert this is impossible. It is not. The read-only mainline_judge login this submission actually publishes refuses the same statement at SQLSTATE 42501 — measured on 2026-08-11 and recorded in evidence/deploy/judge-run.json under divergences — so the credential a judge is handed is the tighter of the two. That does not make N01 a pass, and it is not scored as one here.

It is recorded, not rounded off. Closing it means revoking a grant on submission eve, and a negative suite that has quietly gone green is the worst artefact in a repository, because it reads as the strongest.

## What this proves, and what it does not

**It proves** that CockroachDB's own managed endpoint answers questions about MAINLINE's audit views, over a tool surface Cockroach Labs wrote and we did not, with every statement screened against a documented envelope before it leaves and with the server — not our client — doing the refusing on the negatives.

**It does not prove that a judge can read our ledger over MCP, and no wording here should ever suggest otherwise.**

Our MCP credential is read from `CC_API_KEY` at run time and is recorded nowhere in this repository: it is an account-level CockroachDB Cloud service-account key, not a database login. Its own tool list carries create_database, create_table and insert_rows, and list_clusters enumerates every cluster the account owns. It is therefore **not publishable**, and this repository does not publish it.

So repeatability has three legs and no fourth:

1. **This transcript** — you are reading it, and it needs no credential.
2. **The mechanism** — reproduce it with **your own** key against **your own** cluster. The client configuration is one JSON block in [`MCP-CONFIG.md`](../../verticals/mainline/demo/judge/MCP-CONFIG.md) §1; swap the `mcp-cluster-id` for one of yours and it answers for you. What reproduces is the mechanism, not our data.
3. **Our data is Path B** — the read-only `mainline_judge` pgwire login, published to judges in the submission form, whose whole reach is the fourteen `mainline_audit` views and nothing else. `MCP-CONFIG.md` §4 is the command line. **Path A is the mechanism, Path B is our data.**

## The three write verbs, and why they were never called

`create_database`, `create_table`, `insert_rows` are on the live tool list. That is precisely why the key is an account credential rather than a read-only one. This capture called **0** of them, and the prohibition is enforced rather than promised: an `httpx` request hook parses every outgoing JSON-RPC body and aborts the request before transmission if the tool named is one of the three. See `session.json` → `read_only.enforced_how`.

The measured live shape of `insert_rows` is `{database, query}` — a full `INSERT` statement. Our typed write method takes no parameter that names a table, by design. Expressing it on the live shape means building SQL inside the one method whose entire published guarantee is that it cannot. We did not, and `tools-schema.json` records the divergence instead.

That is one of **5** divergences in `tools-schema.json` → `divergences`, each carrying a `derived_from` predicate over the schemas in the same file — so a reader re-derives every one of them from the artefact rather than taking our word for it. The one that mattered was ours: our client sent the SQL under the argument name `statement`, and the live schema requires `query`. The guess is not erased — it is preserved, named and dated as `DOCUMENTED_DIALECT` in `packages/mainline-mcp/src/mainline_mcp/client.py`, and a test asserts it differs from the measured dialect in precisely that one field.

## Read this directory in under a minute

```bash
# the twelve tools and their required arguments, from the committed capture
python -c "import json;d=json.load(open('evidence/mcp/tools-schema.json'));print([(t['name'],t['required']) for t in d['tools']])"

# every question, its outcome and its verdict
python -c "import json;d=json.load(open('evidence/mcp/pack-run.json'));print([(r['qid'],r['outcome'],r['verdict']) for r in d['results']])"
```

To re-take the capture against your own cluster, set `MAINLINE_MCP_API_KEY` and `MAINLINE_MCP_CLUSTER_ID` and run `python scripts/submission/capture_mcp_evidence.py`.

## This directory is additive

`evidence/deploy/judge-run.json` and `evidence/deploy/judge-access.json` are unchanged by this capture. They are the first MCP transcript this project took, on 2026-08-11, and they are cited from `docs/TOOL-USAGE.md` and `MCP-CONFIG.md`. This directory is where a reader looking for the *tool* finds it; it does not replace them.

## Credential hygiene

This page, and each JSON file beside it, carries a self-scan that its own writer gates on. The writer refuses to emit rather than emit a match.

```json
{
  "assertion": "no field in this file is credential-shaped",
  "method": "the serialised artefact was searched for (a) the live Managed-MCP service-account key verbatim, as a substring so a value embedded in a longer string is caught too, (b) any connection string whose userinfo still carries a password rather than the redacted form, and (c) any bare token of 24+ characters mixing upper case, lower case and digits — the shape a generated secret has. UUIDs are excluded by shape, not by an allowlist of values, which is why the cluster id survives the scan. bytes_scanned counts the artefact body as it was scanned, before this block was appended; after the write the file was re-read FROM DISK and scanned again, and a disagreement deletes the file rather than reporting a pass.",
  "self_scanned": true,
  "bytes_scanned": 9922,
  "key_was_in_scope_this_run": true,
  "matches": 0,
  "holds": true
}
```
