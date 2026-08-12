<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# MCP-CONFIG — pointing your own MCP client at this ledger

**Audience: a judge who wants to interrogate the MAINLINE demo database from their own tooling
rather than from ours.** Two paths are described. Both are measured, both work, and the page says
plainly which credential goes where and which one we will not give you.

Everything on this page was measured on **2026-08-11** against CockroachDB Cloud Basic
`mainline-dev`, `aws-ap-southeast-1` (Singapore), v26.2.5. The artefacts are
[`evidence/deploy/judge-access.json`](../../../../evidence/deploy/judge-access.json) and
[`evidence/deploy/judge-run.json`](../../../../evidence/deploy/judge-run.json).

The configuration block in §1 is **byte-identical to the one in
[`docs/deploy/JUDGE-PACK.md`](../../../../docs/deploy/JUDGE-PACK.md) §4** — cross-checked
2026-08-13. If the two ever diverge, that is a defect in whichever was edited last, and this
file is the one with the field-by-field explanation.

---

## 0. Which path is yours

| | Path A — Managed MCP | Path B — psql / any SQL client |
|---|---|---|
| Credential | **your own** CockroachDB Cloud API key, against **your own** cluster | **ours**, published to you: `mainline_judge` |
| Points at our data | no | **yes** |
| Reproduces the mechanism | yes | yes |
| Set-up | one JSON block, below | one command line, §4 |

If you want to read **our** ledger, you want **Path B**. Path A is here because "we use the
CockroachDB Managed MCP Server" is a claim we make in the submission, and a claim about a tool
should come with the configuration that reproduces it. §3 explains, without hedging, why our MCP
key is not the one we hand out.

---

## 1. Path A — the copy-pasteable client configuration

Drop this into your MCP client's server configuration. It is the exact wiring that produced
`evidence/deploy/judge-run.json`, with our cluster id left in so you can see the real shape; swap
`mcp-cluster-id` for one of your own clusters and it will answer for you.

```json
{
  "mcpServers": {
    "cockroachdb": {
      "type": "http",
      "url": "https://cockroachlabs.cloud/mcp",
      "headers": {
        "Authorization": "Bearer ${COCKROACH_CLOUD_API_KEY}",
        "mcp-cluster-id": "7cfc9ee9-f9b4-413d-bcad-d81fca2c6c7e"
      }
    }
  }
}
```

The same thing for a CLI that takes flags instead of a file:

```bash
claude mcp add --transport http cockroachdb https://cockroachlabs.cloud/mcp \
  --header "Authorization: Bearer $COCKROACH_CLOUD_API_KEY" \
  --header "mcp-cluster-id: 7cfc9ee9-f9b4-413d-bcad-d81fca2c6c7e"
```

### Every field, and what it is for

| field | value | why it is that value |
|---|---|---|
| `type` / `--transport` | `http` | The server speaks **Streamable HTTP**, not stdio and not SSE-only. It answers a `POST` with an `text/event-stream` body carrying one JSON-RPC message per `data:` line — a client that assumes a plain JSON response reads nothing. |
| `url` | `https://cockroachlabs.cloud/mcp` | Cockroach Labs' hosted endpoint. It is not per-cluster and not per-region; the cluster is selected by the header below, not by the path. |
| `Authorization` | `Bearer <your Cloud API key>` | A **CockroachDB Cloud service-account key**, created in the Cloud console under Access Management → Service Accounts. It is an *account* credential, not a database login: see §3. |
| `mcp-cluster-id` | `7cfc9ee9-f9b4-413d-bcad-d81fca2c6c7e` | Pins the session to one cluster. Ours is shown so the configuration is complete and checkable. Without it the server has no target; with a cluster your key does not own, it refuses. |
| `MCP-Protocol-Version` | `2025-06-18` | Sent by the client after `initialize`. Measured against the live server today: it answers `initialize` with `protocolVersion: 2025-06-18` and `serverInfo: {"name": "cockroachdb-cloud", "version": "1.0.0"}`. Most clients send this for you. |
| `Mcp-Session-Id` | echoed | The server issues it in the `initialize` response headers and expects it on every later request. Again, most clients handle this; if you are writing the calls by hand, carry it. |

Measured today, first byte to `initialize`: **591 ms** from Australia to Singapore. A
`select_query` round trip on the pack's questions ran **281–968 ms**, median **691 ms**.

### What it exposes — twelve tools, enumerated

`tools/list` returned exactly these, today:

```
create_database   create_table      explain_query     get_cluster
get_table_schema  insert_rows       list_clusters     list_databases
list_tables       select_query      show_running_queries  show_statement
```

The two the judge pack uses are **`select_query`** and **`explain_query`**. Both take
`database` and `query`.

> **A trap worth naming, because it cost us a debugging session.** The live server requires the
> statement under the argument name **`query`** and makes **`database` mandatory**. Our own client
> package `packages/mainline-mcp` sends `statement=` and omits `database=`, and the server answers
> `must contain exactly one statement`. The session, the auth and the cluster pin are all fine —
> the argument names are not. If you write your own calls, use `query` and `database`.
>
> A second one: `explain_query` **prepends its own `EXPLAIN`**. Sending a statement that already
> begins with `EXPLAIN` returns `EXPLAIN is not allowed for EXPLAIN statements`.

### What it cannot do

* **Three schemas are blocked by the server, by name, before SQL privilege is consulted.**
  `crdb_internal`, `pg_catalog` and `information_schema` all come back
  `query references a restricted schema: access to "X" is blocked for security reasons`. That is
  a stronger guarantee than a grant, because no privilege change on our side can weaken it.
* **It does not run as `root`.** `SELECT current_user` over the endpoint answers **`managed-mcp`**
  — a dedicated, purpose-built SQL identity, not the cluster owner. That answers day-1 check GT-10
  in [`FALLBACK.md`](FALLBACK.md), which records it as unanswered and assumes the pessimistic case.
* **It is not read-only.** `create_database`, `create_table` and `insert_rows` are in the tool
  list above and they work. §3.
* **It will not authenticate with our key**, because we do not publish our key. Pointed at your own
  cluster with your own key, everything on this page reproduces.

### Where the credential goes

**Into your MCP client's own secret store, or an environment variable your shell exports — never
into a file you commit.** The `${COCKROACH_CLOUD_API_KEY}` above is written as an interpolation on
purpose: the JSON block is safe to check in, and the value is not. A Cloud API key in a repository
is a Cloud API key published, and rotating it is the only remedy — which is a lesson this project
learned about its *own* credential, on the record, in
[`docs/deploy/JUDGE-PACK.md`](../../../../docs/deploy/JUDGE-PACK.md) §2.1.

---

## 2. What the pack asked over this channel, and what came back

`evidence/deploy/judge-run.json`, regenerated **2026-08-11**, ran all sixteen questions from
[`QUESTIONS.yaml`](QUESTIONS.yaml) over this channel — loaded through the pack's own loader, so
they are the pack's questions and not a re-typed copy.

```
mcp   15/16 as expected   (identity managed-mcp)
sql   12/16 as expected   (identity mainline_judge, over pgwire)
```

The two runs are **complementary, not redundant**, and each covers the other's gap:

| question | over MCP | over pgwire as `mainline_judge` | reading |
|---|---|---|---|
| Q10, Q10C (plan proofs) | **PASS**, 18-row plans showing a vector index scan | `42501` | the judge login holds no base-table privilege — the failure *is* the grant working |
| N01 `mainline_qa` | **FAIL — readable** | PASS (`42501`, no `USAGE`) | a real gap, §2.1 |
| N02 `crdb_internal` | PASS (server blocklist) | PASS (`42501`) | both transports refuse |
| N03 `pg_catalog`, N04 `information_schema` | PASS (server blocklist) | fail — readable by any login | per-user-filtered catalogues; the property belongs to the MCP transport |

### 2.1 The one that does not hold

`GRANTS.yaml` S14 and the pack's own envelope state that `mainline_qa` — per-person deliberation
measurement — is reachable by no automated account on any tier. **Over Managed MCP it is
readable.** `managed-mcp` runs `SELECT count(*) FROM mainline_qa.v_disposition_profile`
successfully and finds zero rows.

Zero rows is not a refusal, and the difference is the whole point of asking. The credential we
publish to you refuses the same statement with `42501`, so nothing *you* can reach is affected —
but the claim as written is wider than the measurement supports, and it is recorded under
`divergences` in the evidence rather than quietly narrowed.

---

## 3. Why our MCP key is not published, stated plainly

The credential that reaches `https://cockroachlabs.cloud/mcp` is a **CockroachDB Cloud
service-account key**. It is not a database login and it is not scoped to one database.

Measured, with our key, on the live demo cluster:

* the tool list carries `create_database`, `create_table` and `insert_rows`;
* `create_database` returned `{"success": true}` — a database really was created on the demo
  cluster and dropped again in the same session;
* `list_clusters` enumerates **every cluster the account owns**.

[`FALLBACK.md`](FALLBACK.md) pre-committed to a degrade path if the key could not be published, on
the assumption that the blocker would be tier availability or Cockroach Labs' terms. **It is
neither.** Managed MCP works fine on Basic. The key is simply far too powerful to hand to a
stranger, and that file's own rule — *no key is ever published on the demo cluster; not a weaker
one, none* — is what governs.

So the credential you get is the read-only SQL login, and §4 is how you use it.

---

## 4. Path B — no MCP client required

Everything the judge pack asks over MCP, you can ask over plain pgwire. This is the credential we
publish.

```bash
psql "postgresql://mainline_judge:<PASSWORD-FROM-THE-SUBMISSION-FORM>@mainline-dev-31219.j77.aws-ap-southeast-1.cockroachlabs.cloud:26257/mainline_demo?sslmode=verify-full"
```

Replace `<PASSWORD-FROM-THE-SUBMISSION-FORM>` with the value in the submission's credentials
field. **It is not in this repository and it is not on this page.** It was rotated on 2026-08-11
and the reason is recorded in [`JUDGE-PACK.md`](../../../../docs/deploy/JUDGE-PACK.md) §2.1. That
token is the only placeholder on this page; the demo URL, which is the other one in `JUDGE-PACK.md`,
does not appear here at all because this path needs no deployment of ours.

The first thing worth typing:

```sql
-- what the database is refusing to merge right now
SELECT site_id, state, permits, open_blocking, open_residue
  FROM mainline_audit.v_open_gate_summary LIMIT 25;

-- and a refusal you can see with your own eyes
SELECT count(*) FROM mainline.permit;
-- ERROR:  user mainline_judge does not have SELECT privilege on relation permit
-- SQLSTATE: 42501
```

The full reach is the fourteen `mainline_audit` views and nothing else, verified from the other
side on 2026-08-11: **14 of 14 readable, 6 non-empty; 11 of 11 refusals at `42501`**, covering
`SELECT` on a base table, `INSERT`, `CREATE TABLE` and `DROP VIEW`.
[`JUDGE-PACK.md`](../../../../docs/deploy/JUDGE-PACK.md) §2 has the table, and §2.3 records the
same four SQLSTATEs re-derived on a local v26.2.5 node on 2026-08-13 against a role of the same
shape — so they are a property of the engine and the grant, not of one cluster on one afternoon.

**Fourteen is the count of `GRANT SELECT` statements** in
`verticals/mainline/db/demo/judge_grants.sql`, lines 136–149. That file holds exactly one other
grant of any write privilege: a `GRANT INSERT` at line 155 on `mainline_meas.external_attestation`
— **a relation with no producer migration anywhere in the 271-file chain**, so the statement skips
and the login ends up with **no write surface at all**. [`FALLBACK.md`](FALLBACK.md) §0.3 shows the
derivation; it is narrower than this directory's documents used to describe, and it is the true
position.

---

## 5. One discrepancy in this directory, recorded and not patched

[`PACK.md`](PACK.md) describes a second cluster, **`mainline-verify`**, as the throwaway the pack
runs against. **It does not exist.** `list_clusters` over the Cloud API returns exactly one:
`mainline-dev`, `7cfc9ee9-f9b4-413d-bcad-d81fca2c6c7e`, Basic, Singapore — the cluster this page
configures.

This deployment uses that one cluster, because a second Basic cluster splits the same free
allowance to buy isolation we do not need: every row is synthetic and the published login is
read-only. `PACK.md` is generated from `QUESTIONS.yaml`, which belongs to the agents-mcp domain;
the deploy worker that measured this **records the discrepancy and does not edit the generator**.
Anyone reading `PACK.md` should read `mainline-dev` wherever it says `mainline-verify`.
[`FALLBACK.md`](FALLBACK.md) §0.2 carries the same correction, and notes that it *strengthens*
the no-published-key rule rather than weakening it: the film was shot against the only cluster
there is.

### 5.1 · A correction to this file's own previous claim

An earlier revision of this section stated that *`FALLBACK.md` refers to "eighteen questions"*.
**It does not, and it never did.** Before this correction was written on 2026-08-13,
`git grep -ni eighteen -- verticals/mainline/demo/judge/` returned exactly one line — the footnote
here making the claim, not the claim itself. (It now returns the three corrections, this one
among them; that is what a self-referential grep does, and it is why the finding is stated with
its date rather than as a standing command.) What was true is that `FALLBACK.md` stated no total
at all, which is a different and smaller defect; it now states the count explicitly, in its §0.1.

The number, counted out of [`QUESTIONS.yaml`](QUESTIONS.yaml) and corroborated by
`evidence/deploy/judge-run.json`'s `questions / positive / negative` keys — written by the pack's
own loader, not by hand — is **sixteen: twelve positive (`Q01`–`Q10C`), four negative
(`N01`–`N04`)**. §2 above uses the same figure.
