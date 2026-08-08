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
server-side triggers (risk AR-5, day-1 check `GT-09`).

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

**Not proven here:** anything that requires the live service. No MCP service-account key
exists on the build machine (`VERIFY.md`). Specifically:

- The **limit values** are documentation-derived, not re-measured. Where documentation and
  behaviour could disagree, this client is the stricter of the two by construction: it
  refuses at or below every documented threshold and never above one.
- The **tool argument names** (`statement`, `table`, `rows`, `limit`, `database`) are our
  best reading of the documented surface. They are isolated in one injectable
  `ToolDialect` object rather than spelled inline in seven methods, so a live-surface
  difference is a one-line change and never a hidden guess.
- The **response envelope** of `select_query` is parsed tolerantly (structured content, or
  JSON in a text block, under `rows` / `results` / `data` / `records`). What is *not*
  tolerant is the prober: an unrecoverable envelope is a breach.

`tests/integration/mcp/` closes all three the moment a key exists, and **skips with a
reason rather than passing** until then.

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
