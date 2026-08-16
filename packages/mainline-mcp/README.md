<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: Apache-2.0
-->

# `mainline-mcp`

**CockroachDB's Managed MCP Server, with its limits made into types.**

The Managed MCP Server does not raise when a statement exceeds a limit — it **truncates**.
A truncated answer about how many precursors went undispositioned is indistinguishable, on
the wire, from a small one. In MAINLINE a silently truncated aggregate is a safety defect,
so every documented limit is refused on *this* side of the network, by a distinct exception
class that names the limit and carries the number that broke it.

```python
from mainline_mcp import Client, StatementTooLong, ForbiddenSchema

client = Client.connect(api_key=..., cluster_id="cl-...")

client.select_query("SELECT * FROM crdb_internal.jobs")
# ForbiddenSchema: forbidden_schema: the MCP tools cannot reach this schema; ask a
# mainline_audit view instead — that constraint is what makes the audit views an API
# rather than a bypass (limit [...], observed ['crdb_internal'])
```

---

## What is in here

| Module | What it is |
|---|---|
| `limits` | Every documented Managed-MCP limit as a constant; a SQL scanner that reads a statement without transmitting it; one exception class per limit. |
| `client` | One pinned cluster, one statement per call, one writable table. Streamable HTTP transport, plus two deliberately-named probes for the negative suite. |
| `catalogue` | The audit-surface contract (`spec/mcp/audit-surface.contract.yaml`) loaded and made strict, with divergence reporting against `ARCHITECTURE.md` §17. |
| `budget` | The response-budget prober: measures each contracted view's **actual** bytes and rows and fails at 8 192 bytes — 80 % of the 10 240-byte cap. |
| `auditor` | The nine questions a general counsel asks, each bound to one contracted view, routed deterministically, completeness stated on every answer. |

## The three shapes that carry the package

**One cluster.** The pin is a constructor argument, it goes out as `mcp-cluster-id` on
every request, and any tool argument naming a different cluster is refused before
transmission. The server is documented to fail such a call as well; refusing here too
means the failure is attributable to us attempting it, and the assertion has something to
catch on a machine with no key.

**One statement, within every documented limit.** 16 384 characters, exactly one statement
per call, no `EXPLAIN ANALYZE`, no `LIMIT ALL`, no explicit `LIMIT` above 10 000, `SHOW`
and the list verbs capped at 100, and no reference to `system`, `crdb_internal`,
`pg_catalog`, `information_schema` or `pg_extension`. The scanner blanks string literals,
dollar-quoted bodies and comments first, so `WHERE code = 'CY-01; CY-02'` is one statement
and `-- unlike crdb_internal.jobs` is not an access attempt. A control operators route
around is not a control.

**One writable table.** `Client.insert_external_attestation(rows)` has **no parameter that
names a table** — `mainline_meas.external_attestation` is a constant in the method body.
"Insert somewhere else" is not a call the supported API can express. That table is
trigger-free by construction, so the design is correct whether or not `insert_rows` fires
server-side triggers (risk AR-5, day-1 check `GT-09`). The live `insert_rows` wants a full
INSERT statement instead of `{table, rows}` — measured 2026-08-16, kept as a stated
divergence rather than closed by generating SQL here. See *Verification status*.

## The budget, and why it is 8 KiB and not 10

The server caps a response at 10 240 bytes. The prober fails at **8 192** — 80 % — because
a limit tested at 100 % breaches in front of a judge the first time the corpus grows.
Failing at 80 % means the alarm fires with 20 % of headroom left and lands in CI on a day
when someone can fix it (decision A11, risk AR-6).

Five conditions are breaches, and three of them are what make this a verification rather
than a size check:

- `byte_budget` / `row_budget` — measured bytes or rows above the contract.
- `row_count_undetermined` — the rows could not be recovered from the response envelope.
  **A failure, not a skip**: a view whose row count cannot be measured has not been
  verified.
- `truncation_flag_missing` — the contract promises a completeness flag and the rows do
  not carry it. A reader cannot tell a complete answer from a truncated one without it.
- `tool_error` / `response_cap` — the server refused, or the response arrived exactly at
  the cap, which is the shape a truncation has.

The **worst observed row** is recorded on every measurement, breach or not: AR-6's accepted
residual is that one pathological row (a very long site code) can spike a view, and the
cause has to be nameable when it happens.

## The auditor persona

Deterministic. Nine questions, nine views, cue-phrase and token scoring, no model and no
sampling — the agent in this story is the judge's own, and `ARCHITECTURE.md` §10.3 is
explicit that the auditor path contains none of our code.

A question can never become SQL: `ask()` resolves text to a `ViewSpec` and then sends
*that view's generated statement*. An unroutable question is a refusal, never a guess,
because a wrong view answered confidently is worse than no answer.

Every rendered answer states its completeness in one of five states — complete,
incomplete (with the row count and a note that the numbers beneath are lower bounds), the
promised flag absent, the view carries no flag by contract, or the response was
unparseable. None of them is silence.

## Verification status — what is proven and what is not

**Proven offline, on this machine, with no credential:** the scanner and every refusal;
the contract loader; the prober's verdicts at fixed byte counts; the persona's routing and
completeness rendering; and the *real* Streamable HTTP transport — handshake, session
header, SSE framing, cluster header — driven against `httpx.MockTransport`.

### The tool argument names are MEASURED, dated 2026-08-16

They used to be "our best reading of the documented surface". They are not any more. On
**2026-08-16** this package's own `Client` ran `initialize` and `tools/list` against
`https://cockroachlabs.cloud/mcp`, and the names below were read out of the server's own
`inputSchema` — a stronger source than either our prose reading or the published
documentation.

```
initialize    protocolVersion 2025-06-18
              serverInfo {"name":"cockroachdb-cloud","version":"1.0.0"}
tools/list    12 tools
select_query  SELECT current_user            -> {"rows":[{"u":"managed-mcp"}]}
select_query  SELECT * FROM mainline_audit.v_open_gate_summary LIMIT 25
              -> 1 row, 425 bytes, 584 ms, rows_complete = true
```

| verb | `required` on the wire | what we send |
|---|---|---|
| `select_query` | `database`, `query` | `query`, `database` |
| `explain_query` | `database`, `query` | `query`, `database` |
| `show_statement` | `query` | `query`, `database` when set |
| `list_databases` | — | `limit` |
| `list_tables` | `database` | `database`, `limit` |
| `get_table_schema` | `database`, `table` | `database`, `table`, `schema` when given |
| `show_running_queries` | — | nothing |
| `insert_rows` | `database`, `query` | **not sent — see the divergence below** |

**The reading was wrong in exactly one field**, and the design that predicted this is the
reason it cost one line. The sentence in the previous version of this file —

> isolated in one injectable `ToolDialect` object rather than spelled inline in seven
> methods, so a live-surface difference is a one-line change and never a hidden guess

— is now cashed. `ToolDialect.statement` moved from `"statement"` to `"query"`. Nothing
else in the dataclass moved. The guess we published is **not erased**: it is kept as
`DOCUMENTED_DIALECT`, dated and commented, and `tests/test_client.py` asserts that the two
constants differ in precisely that one field.

The server's own five-word verdict on the old name, re-measured on the day:

```
select_query {"database":"mainline_demo","statement":"SELECT 1 AS one"}
   ->  ToolCallFailed: tools/call: must contain exactly one statement
```

Not an auth failure, not a cluster failure — the required `query` property was simply
absent, so the server saw no statement at all.

Three call-site corrections came out of the same measurement:

- **`select_query` and `explain_query` have no `limit` argument.** The schema says *"Use
  LIMIT/OFFSET in your query for pagination."* We never sent one on those two; the row
  ceiling is read out of the `LIMIT` the caller wrote, and that is now stated rather than
  assumed.
- **`show_statement` and `show_running_queries` have no `limit` argument either**, and we
  were sending one. It is no longer transmitted. The 100-row ceiling is still refused
  client-side — it is now *ours*, enforced here, and no longer described as the server's.
- **`explain_query` takes the query to explain, not an `EXPLAIN` statement.** A statement
  beginning with `EXPLAIN` returns `EXPLAIN is not allowed for EXPLAIN statements`; the
  bare `SELECT` returned a 4 421-byte plan. This client does **not** strip the keyword for
  you — rewriting a caller's SQL is the silent helpfulness this package exists to refuse.
  `EXPLAIN ANALYZE` is still refused before transmission.

`database` is **required** on `select_query` and `explain_query`, and every caller in this
repository asks its question of a *view*. So `Client(transport, database=...)` /
`Client.connect(..., database=...)` carries it. Unset, the argument is omitted exactly as
before, which is what keeps every offline caller working unchanged.

### The write verb: a divergence recorded, not closed

Measured on the same connection, `insert_rows` requires `{database, query}` where `query`
is *"The INSERT statement to execute. Include the full table name with optional schema
prefix …"*. There is no `table` property and no `rows` property.

Speaking that shape means composing an INSERT statement — with a table name inside it —
in the one method whose entire published guarantee is that *no parameter names a table*.
That guarantee is worth more than the call. So:

> **`Client.insert_external_attestation` is unchanged, this call has not been sent to the
> live server, and no claim is made that it succeeds there.** The typed write surface is
> the product; the live argument shape is recorded beside it.

`tests/test_client.py::TestWriteBinding` asserts both halves — that the live `required`
list is `("database", "query")`, and that our signature is still `(self, rows)` — so the
passing suite cannot be misread as "the live write works".

### Still not proven here

- The **limit values** are documentation-derived, not re-measured. Where documentation and
  behaviour could disagree, this client is the stricter of the two by construction: it
  refuses at or below every documented threshold and never above one.
- The **response envelope** of `select_query` is parsed tolerantly (structured content, or
  JSON in a text block, under `rows` / `results` / `data` / `records`). What is *not*
  tolerant is the prober: an unrecoverable envelope is a breach. The 2026-08-16 run
  recovered rows from the live `select_query`, `show_statement`, `list_databases` and
  `get_table_schema` responses through this path.
- The **auditor persona** and the **byte-budget prober** are proven against
  `httpx.MockTransport` only.

`tests/integration/mcp/` closes the rest the moment a key is present in the environment,
and **skips with a reason rather than passing** until then.

## Not depended on: the `mcp` SDK

This client speaks four JSON-RPC methods to one server and must state a client-side
refusal for every documented limit *before a byte leaves the process*. An SDK that
transports whatever it is given would move those refusals to the far side of the network,
where a truncated answer is indistinguishable from a small one. The official SDK belongs
in `packages/trappoint-mcp` — our own MCP **server** — and it is pinned there.

## What this package does not claim

> The Managed MCP identity is assumed **admin-equivalent** and RLS is assumed **not** to
> apply. `mainline_audit` views are therefore designed to be safe if read in full,
> `mainline_qa` never receives an account, and **we never market MCP as site-scoped.**

---

Licence: Apache-2.0. See `VERIFY.md` at the repository root for the three verification
tiers and the scoped-key policy.
