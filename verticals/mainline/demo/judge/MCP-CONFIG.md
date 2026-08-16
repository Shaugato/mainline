<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# MCP-CONFIG — pointing your own MCP client at this ledger

**Audience: a judge who wants to interrogate the MAINLINE demo database from their own tooling
rather than from ours.** Two paths are described. Both are measured, both work, and the page says
plainly which credential goes where and which one we will not give you.

Everything on this page was measured against CockroachDB Cloud Basic `mainline-dev`,
`aws-ap-southeast-1` (Singapore), v26.2.5, on **two dates that are both kept**:

* **2026-08-11** — the sixteen-question pack driven over this channel end to end. Artefacts:
  [`evidence/deploy/judge-access.json`](../../../../evidence/deploy/judge-access.json) and
  [`evidence/deploy/judge-run.json`](../../../../evidence/deploy/judge-run.json). Those two
  files are **not superseded and are not moved** — they are the transcript, they are cited from
  [`docs/TOOL-USAGE.md`](../../../../docs/TOOL-USAGE.md) and
  [`docs/demo/ON-SCREEN-CLAIMS.md`](../../../../docs/demo/ON-SCREEN-CLAIMS.md) as well as from
  here, and nothing on this page replaces them.
* **2026-08-16** — a read-only re-capture of the same endpoint, taken on submission eve, which
  **re-confirmed the handshake and the twelve-tool list byte for byte** and settled one thing the
  2026-08-11 pass had only *read out of prose*: the tools' argument names, taken this time from
  the server's own `tools/list` JSON Schema. §1.2 is that measurement and it is the reason this
  page was re-dated. No write verb was called; no credential was printed. Artefacts:
  [`evidence/mcp/`](../../../../evidence/mcp/README.md) — `session.json` (the handshake and the SQL
  identity), `tools-schema.json` (all twelve tools with their **full** `inputSchema`, and the
  divergences derived from it), `pack-run.json` (the same sixteen questions, this time through the
  pack's own runner), plus `auditor-live.json` and `budget-live.json`. **That directory is the
  primary artefact for this page and it is additive** — it is where a reader looking for the MCP
  tool will look, rather than under a directory whose name says *deployment*.

The configuration block in §1 is **byte-identical to the one in
[`docs/deploy/JUDGE-PACK.md`](../../../../docs/deploy/JUDGE-PACK.md) §4** — cross-checked
2026-08-13 and re-checked 2026-08-16, character for character including the CLI form beneath it.
If the two ever diverge, that is a defect in whichever was edited last, and this file is the one
with the field-by-field explanation. Re-derive it rather than believing this sentence:

```bash
python - <<'PY'
import pathlib, re
HERE = "verticals/mainline/demo/judge/MCP-CONFIG.md"
PACK = "docs/deploy/JUDGE-PACK.md"

FENCE = chr(96) * 3     # spelled this way so the snippet survives being pasted INTO a fence

def block(path, lang, opener):
    """The one fenced block of *lang* whose body BEGINS with *opener*."""
    text = pathlib.Path(path).read_text(encoding="utf-8")
    pattern = FENCE + r"(\w+)\n(.*?)" + FENCE
    hits = [m.group(2) for m in re.finditer(pattern, text, re.S)
            if m.group(1) == lang and m.group(2).startswith(opener)]
    assert len(hits) == 1, f"{path}: expected 1 {lang} block opening {opener!r}, got {len(hits)}"
    return hits[0]

for lang, opener in (("json", "{"), ("bash", "claude mcp add")):
    print(f"{lang:>5} block identical:", block(HERE, lang, opener) == block(PACK, lang, opener))
PY
```

It prints `True` twice. **It selects by the block's opening token rather than by searching for
text inside it, and it asserts rather than indexing** — so a second candidate block turns the
check red instead of silently comparing the wrong pair, and the check does not match *itself*
the way a naive `grep` for `mcpServers` would. That failure mode is not hypothetical: the
identical mistake is recorded, with its correction, in
[`JUDGE-PACK.md`](../../../../docs/deploy/JUDGE-PACK.md) §0.5.

---

## 0. Which path is yours

| | Path A — Managed MCP | Path B — psql / any SQL client |
|---|---|---|
| Credential | **your own** CockroachDB Cloud API key, against **your own** cluster | **ours**, published to you: `mainline_judge` |
| Points at our data | no | **yes** |
| Reproduces the mechanism | yes | yes |
| Set-up | one JSON block, §1 — or one command, §1.3 | one command line, §4 |

If you want to read **our** ledger, you want **Path B**. Path A is here because "we use the
CockroachDB Managed MCP Server" is a claim we make in the submission, and a claim about a tool
should come with the configuration that reproduces it. §3 explains, without hedging, why our MCP
key is not the one we hand out.

**There is no third row, and its absence is the honest part.** A judge cannot read MAINLINE's
ledger over MCP with a credential we hand out, because we do not hand one out — §3. Path A is
*mechanism*, Path B is *our data*, and no wording on this page should ever suggest otherwise.

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
| `Authorization` | `Bearer <your Cloud API key>` | A **CockroachDB Cloud service-account key**, created in the Cloud console under Access Management → Service Accounts. It is an *account* credential, not a database login: see §3. `${COCKROACH_CLOUD_API_KEY}` is a name **you** choose in your own client's secret store — it is not a name this repository reads. The one our scripts read is `CC_API_KEY`, §1.3. |
| `mcp-cluster-id` | `7cfc9ee9-f9b4-413d-bcad-d81fca2c6c7e` | Pins the session to one cluster. Ours is shown so the configuration is complete and checkable. Without it the server has no target; with a cluster your key does not own, it refuses. |
| `MCP-Protocol-Version` | `2025-06-18` | Sent by the client after `initialize`. Measured against the live server on 2026-08-11 **and again on 2026-08-16**, both times identical: it answers `initialize` with `protocolVersion: 2025-06-18` and `serverInfo: {"name": "cockroachdb-cloud", "version": "1.0.0"}`. Most clients send this for you. |
| `Mcp-Session-Id` | echoed | The server issues it in the `initialize` response headers and expects it on every later request. Again, most clients handle this; if you are writing the calls by hand, carry it. |

**Measured 2026-08-11**, first byte to `initialize`: **591 ms** from Australia to Singapore. A
`select_query` round trip on the pack's questions ran **281–968 ms**, median **691 ms**.

**Re-measured 2026-08-16, read-only, and it is the same endpoint answering the same way:**

```
initialize        HTTP 200   protocolVersion 2025-06-18
                             serverInfo {"name":"cockroachdb-cloud","version":"1.0.0"}
tools/list        HTTP 200   12 tools, byte-identical to the 2026-08-11 list
select_query      HTTP 200   SELECT current_user  ->  {"rows":[{"u":"managed-mcp"}]}
select_query      HTTP 200   SELECT count(*) FROM mainline_audit.v_open_gate_summary
                             ->  {"rows":[{"n":1}]}   566 ms
```

The last line is the one that matters to a judge and it is worth saying why: it is a
**general-counsel question — *what is the gate refusing right now?* — answered by CockroachDB's
own managed endpoint out of a contracted `mainline_audit` view, with none of MAINLINE's code
anywhere in the read path.** The `1` is the demo's whole subject: one permit that cannot merge.

### 1.1 · What it exposes — twelve tools, enumerated

`tools/list` returned exactly these on **2026-08-11**, and the same twelve again on
**2026-08-16** — re-listed rather than remembered, and byte-identical between the two runs:

```
create_database   create_table      explain_query     get_cluster
get_table_schema  insert_rows       list_clusters     list_databases
list_tables       select_query      show_running_queries  show_statement
```

The two the judge pack uses are **`select_query`** and **`explain_query`**.

### 1.2 · The argument names — MEASURED 2026-08-16 from the server's own JSON Schema

**This section used to be a reading and is now a measurement, and the difference is the point of
the page.** Until 2026-08-16 the argument names here were our best reading of the documented
surface — prose, interpreted. On 2026-08-16 they were taken instead from the `inputSchema` the
server itself returns in `tools/list`, which is a stronger source than either our reading or any
published document, because it is the thing the server validates against.

What it says, quoted from that response:

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

Four consequences, each of which changes what you should type:

1. **The statement goes under `query`, and `database` is mandatory.** All three SQL verbs —
   `select_query`, `explain_query`, `insert_rows` — declare exactly `["database","query"]` as
   required. There is no third required argument on any of them.
2. **`cluster_id` is optional and, with the configuration in §1, must be *omitted*.** Its own
   description says so: *"Required when the MCP config has no cluster_id; otherwise must be
   omitted."* Because the block in §1 pins the cluster in the `mcp-cluster-id` header, passing
   `cluster_id` as a tool argument is the wrong call, not a redundant one.
3. **`select_query` has no `limit` argument at all.** Pagination is `LIMIT`/`OFFSET` written
   *inside* the statement, which its own description spells out. A client that models a `limit`
   parameter is modelling a parameter that does not exist.
4. **`insert_rows` takes a whole INSERT statement**, not a `{table, rows}` pair. That matters to
   this repository more than it will to you, and it is stated plainly in §3.1.

And the negative that pins it — the call that fails, with the server's exact words:

```
select_query {"database":"mainline_demo","statement":"SELECT 1 AS one"}
   ->  {"code": 0, "message": "must contain exactly one statement"}
```

That message is worth reading twice, because it is **misleading about its own cause**: the
statement is perfectly well-formed and there is exactly one of it. The server is reporting that
the `query` argument was absent, and the count it is complaining about is a count of zero. If you
write your own calls and see it, check your argument names before you check your SQL.

> **Where the wrong reading came from, and where it lives, because the repository does not erase
> its own guesses.** Until 2026-08-16 this project's own client package sent the statement as
> `statement=` and omitted `database=`. That was never a typo — it was a reading of prose that
> nobody had put against the wire. The name is isolated in a single injectable `ToolDialect`
> object in `packages/mainline-mcp/src/mainline_mcp/client.py` precisely so a live-surface
> difference would be one edit rather than seven hidden guesses, and
> [`packages/mainline-mcp/README.md`](../../../../packages/mainline-mcp/README.md) is where that
> object's history is kept.
>
> A second trap, unchanged and still worth naming: `explain_query` **prepends its own `EXPLAIN`**.
> Sending a statement that already begins with `EXPLAIN` returns
> `EXPLAIN is not allowed for EXPLAIN statements`.

### 1.3 · Reproduce this yourself — one command, your cluster, your key

Everything in §1.1 and §1.2 is a property of **the server**, not of our cluster, so you can
re-derive all of it against a cluster of your own. Two API keys are never involved: yours reaches
your cluster, ours reaches ours, and neither reads the other's data.

**This is the command that produced [`evidence/mcp/`](../../../../evidence/mcp/README.md), pointed
at you instead of at us:**

```bash
export CC_API_KEY=...                     # your own Cloud service-account key, your shell only
python scripts/submission/capture_mcp_evidence.py \
  --cluster-id YOUR-OWN-CLUSTER-UUID \
  --database defaultdb \
  --out /tmp/your-mcp-evidence
```

**Pass `--out`.** Without it the program writes into `evidence/mcp/`, which is *our* committed
transcript; pointing it somewhere of yours keeps the comparison honest in both directions. Add
`--no-pack` for the handshake and the twelve schemas alone — that half is entirely a property of
the server and needs nothing of ours.

It prints its progress as it goes, so you can compare line for line with what we recorded. Against
our cluster on 2026-08-16 it printed this, and against yours the shape is identical while the
identity and the pack line will differ:

```
capturing against https://cockroachlabs.cloud/mcp, cluster 7cfc9ee9-f9b4-413d-bcad-d81fca2c6c7e, database mainline_demo
  handshake      HTTP 200 305.3 ms  protocol 2025-06-18  identity managed-mcp
  tools/list     12 tools, 5 divergences
  judge pack     15/16 — DIVERGED — KNOWN GAP (exit 1)
  wrote evidence/mcp/session.json       5881 bytes  hygiene holds
  wrote evidence/mcp/tools-schema.json  17829 bytes  hygiene holds
  wrote evidence/mcp/pack-run.json      13382 bytes  hygiene holds
  wrote evidence/mcp/README.md          10989 bytes  hygiene holds
```

**Those four byte counts are the sizes of the committed files**, so `ls -l evidence/mcp/` on a
fresh clone re-derives them without a credential — which is the cheapest way to tell that the
transcript above is a transcript and not a mock-up. The three you will not see are the same three
we did not call: `insert_rows`, `create_database`, `create_table`.

Four things about that program, read out of
[`scripts/submission/capture_mcp_evidence.py`](../../../../scripts/submission/capture_mcp_evidence.py)
rather than remembered:

* **It cannot write to your cluster, and the prohibition is enforced rather than promised.** Every
  outgoing HTTP request passes through a `httpx` request hook that parses the JSON-RPC body and
  raises `WriteVerbAttempted` if the tool named is `insert_rows`, `create_database` or
  `create_table`. Those three are on the live tool list — that is exactly why our key is not
  publishable, §3 — so the guard lives at the transport boundary and not in a comment.
* **The key is read from `MAINLINE_MCP_API_KEY`, falling back to `CC_API_KEY`**, and from a `.env`
  file if you keep one. It is never a command-line argument, so it never reaches your shell history
  or the process table, and the pack subprocess receives it through its environment rather than its
  argv.
* **Every artefact it writes is self-scanned for your credential before the write and re-scanned on
  disk after it**, and a file that fails is deleted rather than shipped. Each carries the result as
  a `credential_hygiene` block you can read.
* **The pack line routes through the pack's own runner** — `verticals/mainline/demo/judge/cli.py run
  --via mcp` → `runner.run_via_mcp` — so the envelope validator, the migration drift check and the
  25-row truncation guard are all in the path.

If you would rather drive only the sixteen questions, without writing an evidence directory, the
older entry point still works and takes the same key:

```bash
export CC_API_KEY=...                     # your own Cloud service-account key, your shell only
python scripts/deploy/judge_access.py judge-run \
  --via mcp \
  --cluster-id YOUR-OWN-CLUSTER-UUID \
  --mcp-database defaultdb \
  --out your-mcp-run.json
```

Three facts about *that* command, read out of
[`scripts/deploy/judge_access.py`](../../../../scripts/deploy/judge_access.py) rather than
remembered — `judge-run`'s MCP branch is at `:1421-1437`:

* The key is read from **`MAINLINE_MCP_API_KEY`, falling back to `CC_API_KEY`** (`:1422`). It is
  never a command-line argument, so it never reaches your shell history or the process table.
* **`MAINLINE_MCP_CLUSTER_ID` in the environment *overrides* `--cluster-id`** (`:1423`). If you
  have that variable set from something else, unset it or the flag is ignored.
* **With no key, it does not pass — it records a NOT-RUN with a reason** (`:1424-1433`), in the
  program's own words: *"With no key this is a NOT-RUN, never a pass: a green negative run with
  nothing to talk to asserts the opposite of what it claims."* `--via mcp` needs no database DSN,
  so the SQL half is simply not attempted.

**What to expect, printed alongside so you can tell success from a plausible-looking failure:**

| you should see | if you see something else |
|---|---|
| `initialize` → HTTP `200`, `protocolVersion 2025-06-18`, `serverInfo {"name":"cockroachdb-cloud","version":"1.0.0"}` | a `401` means the key; a `404` means the URL. Neither is a tier problem — Managed MCP works on Basic, §3 |
| `tools/list` → **12** tools, the twelve named in §1.1 | a different count means Cockroach Labs shipped a change after 2026-08-16, and this page is the stale side |
| `SELECT current_user` → **your** cluster's MCP identity. On ours it is `managed-mcp` | `root` would mean the endpoint's identity model differs on your tier, which would be worth telling us |
| `crdb_internal`, `pg_catalog`, `information_schema` → `query references a restricted schema` | the server blocklist is not ours and no grant of yours can weaken it, so this should hold on any cluster. `pg_extension` and `system` are refused the same way |
| `tools/list` → **5 divergences** against our typed surface | that count compares *the server* with *our client*, so it does not depend on whose cluster you point at. A different number means our client moved, not that yours did |
| a `cluster_id` argument, with the header of §1 set → `cluster_id is set in your MCP config; omit the cluster_id argument` | this is §1.2 reading 2 as the server enforces it, and it is why the configuration block pins the cluster in a header rather than in every call |
| the pack's sixteen questions **mostly FAIL against your cluster** | **that is correct and expected.** They ask about `mainline_audit` views that exist only in our schema. What reproduces here is the *mechanism* — handshake, tool list, argument names, schema blocklist — never our data. §3 |

The last row is the honest one and it is why this is a *mechanism* reproduction rather than a data
reproduction. If you want our data, that is Path B in §4, and it needs no MCP client at all.

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

> **Which run this is, so the two dates are never confused.** Everything in this section is the
> **2026-08-11** sixteen-question run. The **2026-08-16** re-probe in §1.2 was reachability and
> JSON Schema only — it re-listed the tools, read `current_user`, counted one audit view, and
> stopped. **It did not re-drive the pack, and this section is therefore not restated from it.**
> A section that quietly borrowed a fresh date for an old run would be the exact defect this
> repository exists to refuse.

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

* the tool list carries `create_database`, `create_table` and `insert_rows` — **re-confirmed
  2026-08-16**, the same twelve tools, the same three write verbs among them;
* `list_clusters` enumerates **every cluster the account owns** — also a 2026-08-16 reading;
* `create_database` returned `{"success": true}` — a database really was created on the demo
  cluster and dropped again in the same session. **That is a 2026-08-11 measurement and it is
  deliberately not refreshed.** The 2026-08-16 re-probe called **read verbs only**: no
  `create_database`, no `create_table`, no `insert_rows`. Re-running a proof that we can write in
  order to make a page feel current would be running a destructive statement against the
  submission's own demo cluster on submission eve, and a dated measurement is worth more than a
  fresh one taken for a bad reason.

`evidence/deploy/judge-access.json` records the conclusion as a field rather than a paragraph:
`mcp_channel.credential_publishable` is `false`, and the adjacent `mcp_channel.why_not_publishable`
carries the reason in the artefact's own words rather than only in this one. The same pair is in
`evidence/deploy/judge-run.json`. **The JSON pointer is named so you can check it without reading
this page** — `python -c "import json;print(json.load(open('evidence/deploy/judge-access.json'))['mcp_channel']['credential_publishable'])"`.

[`FALLBACK.md`](FALLBACK.md) pre-committed to a degrade path if the key could not be published, on
the assumption that the blocker would be tier availability or Cockroach Labs' terms. **It is
neither.** Managed MCP works fine on Basic. The key is simply far too powerful to hand to a
stranger, and that file's own rule — *no key is ever published on the demo cluster; not a weaker
one, none* — is what governs.

**So there is no configuration of this page under which you read MAINLINE's ledger over MCP with a
credential we gave you.** Path A reproduces the *mechanism* against a cluster of yours; Path B
reads *our data* over pgwire with a credential we do publish. Anything that read as a third option
would be a claim we cannot back, and there is not one.

So the credential you get is the read-only SQL login, and §4 is how you use it.

### 3.1 · One capability that is real, measured, and deliberately not in our request path

`insert_rows` is on the live tool list and its measured argument shape is `{database, query}` — a
**whole INSERT statement**, per §1.2. This repository has exactly one permitted write over MCP:
`mainline_meas.external_attestation`, so that a third party's agent can record the outcome of *its
own* verification into our log. That method's published guarantee is that **no parameter of it
names a table** — "insert into something else" is not a call our supported API can express, which
is a property of the signature rather than a check at run time (the constant is
`EXTERNAL_ATTESTATION_TABLE` in `packages/mainline-mcp/src/mainline_mcp/limits.py`, line `101` as
this page is written — search the name rather than counting to the line, because that file is
under active edit).

Speaking the live `{database, query}` shape would mean constructing SQL inside that one method,
which trades the guarantee for a demonstration. **We did not make that trade, and the consequence
is stated rather than hidden: the typed write verb is not sent over the live surface.** It is real
code with a real test suite against a constructed transport; it is not in the demo's request path,
and this sentence is the whole of the claim.

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
