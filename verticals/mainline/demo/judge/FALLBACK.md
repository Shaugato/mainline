<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: FSL-1.1-ALv2
-->

# If the key cannot be published — what Tier 3 degrades to, decided in advance

Tier 3 rests on one thing we do not control: whether publishing a scoped service-account key
to anonymous verifiers is within Cockroach Labs' terms for the Managed MCP Server. That is
day-1 check **GT-17**, and it is the kind of question that is answered late and answered
once.

So the degrade path is written down now, before the answer is known, and the pack runs the
same either way. A fallback improvised on the day is a fallback that quietly drops a claim;
a fallback written on D-14 is a claim stated at its true strength.

---

## 0 · RESOLVED — GT-17 was answered on 2026-08-11, and **Branch B is in force**

Everything below this section was written before the answer was known and is left standing,
because a pre-commitment you edit after the fact is not a pre-commitment. This section
records what was measured, including the two places where the measurement **contradicts**
what the rest of this page assumed.

| | pre-committed assumption | measured 2026-08-11 |
|---|---|---|
| Is Managed MCP available on the Basic tier? | possibly not — treated as a live risk | **YES.** `initialize` at `https://cockroachlabs.cloud/mcp` → HTTP 200, session established, 591.1 ms, `serverInfo cockroachdb-cloud 1.0.0`, protocol `2025-06-18`, 12 tools |
| Which branch? | either | **Branch B**, but **not for either reason this page anticipated** |
| Why? | Cockroach Labs' terms, or tier availability | **Neither.** The credential that reaches that endpoint is the account's **Cloud service-account key**. Its tool list carries `create_database`, `create_table` and `insert_rows`; `create_database` returned `{"success": true}` against the demo cluster; `list_clusters` enumerates every cluster the account owns. It is simply far too powerful to hand to a stranger |
| GT-10 — which SQL identity does the endpoint run as? | unanswered; the pessimistic case assumed | **`managed-mcp`** — a dedicated user, not `root`, not the database owner. Better than the pessimistic assumption, and the assumption is what shipped |

Artefacts: [`evidence/deploy/judge-access.json`](../../../../evidence/deploy/judge-access.json)
and [`evidence/deploy/judge-run.json`](../../../../evidence/deploy/judge-run.json).

**The rule below held under a branch it was not written for**, which is the only real test of a
pre-commitment. What is published instead is the read-only SQL login `mainline_judge` — degrade
**B1** — documented in [`../../../../docs/deploy/JUDGE-PACK.md`](../../../../docs/deploy/JUDGE-PACK.md)
§2 and [`MCP-CONFIG.md`](MCP-CONFIG.md) §4.

### 0.1 · The pack is **sixteen** questions

Counted out of [`QUESTIONS.yaml`](QUESTIONS.yaml) itself, and corroborated by
`evidence/deploy/judge-run.json`'s `questions / positive / negative` keys, which the pack's own
loader wrote rather than a person:

> **16 questions — 12 positive (`Q01`–`Q10C`) and 4 negative (`N01`–`N04`).**

This page previously stated no total at all. Two other documents — `MCP-CONFIG.md` §5 and
`docs/deploy/JUDGE-PACK.md` §8 — carried a footnote saying this page referred to *"eighteen
questions"*. **It never did.** Before those footnotes were corrected on 2026-08-13,
`git grep -ni eighteen -- verticals/mainline/demo/judge/` returned exactly one line, and it was
the footnote in `MCP-CONFIG.md` asserting the claim — not the claim itself. It now returns only
the three corrections, this one among them. The footnotes were removed rather than propagated.

### 0.2 · `mainline-verify` does not exist

§ *The rule that does not change* below, and [`PACK.md`](PACK.md), describe a second throwaway
cluster called `mainline-verify`. **There is no such cluster.** `list_clusters` over the Cloud
API returns exactly one: `mainline-dev`, `7cfc9ee9-f9b4-413d-bcad-d81fca2c6c7e`, Basic,
Singapore. This deployment uses that one cluster, because a second Basic cluster splits the same
free allowance to buy isolation we do not need: every row is synthetic and the published login is
read-only. Read `mainline-dev` wherever this directory says `mainline-verify`.

That removes the isolation argument for publishing a key, and it does **not** weaken the rule —
it strengthens it, because the film was shot against the only cluster there is.

### 0.3 · The write-surface argument was built on a table that does not exist

This page argues, below, that the Managed MCP write surface is "insert-only and bound to
`mainline_meas.external_attestation`". **Both halves of that sentence are wrong**, and the
correction runs in the same direction as the rule.

* **It is not insert-only.** The measured tool list carries `create_database`, `create_table` and
  `insert_rows`, and `create_database` succeeded. It is a full DDL surface at account scope.
* **It is not bound to `external_attestation`, because that relation has no producer migration.**
  Re-derived over the 271-file chain:

  ```
  $ git grep -l "CREATE TABLE.*external_attestation" -- verticals/mainline/db/migrations/
  (no output)
  $ git grep -n "external_attestation" -- verticals/mainline/db/migrations/
  0089b_standing.sql:131:--    surface is `mainline_meas.external_attestation`.
  ```

  One hit, and it is a comment. `GRANTS.yaml:401` grants `INSERT` on that relation "since `0089`";
  nothing ever created it.

The consequence for the **published** credential is the part worth stating plainly.
`verticals/mainline/db/demo/judge_grants.sql` contains exactly one `GRANT INSERT`, at line 155, on
that same absent relation — so it **skips**, by design and visibly (`judge_grants.sql:84-92`
documents the skip as a contract, because a `GRANT` against an absent relation raises
`42P01 cannot determine the target type` and would abort a whole-file run).

> **`mainline_judge` therefore has no write surface at all — not insert-only, none.**

That is a **narrower and stronger** position than this page originally described, and it is the
true one. Fourteen `GRANT SELECT` statements on `mainline_audit` views, and nothing else.

### 0.4 · One thing B2 promises that the runner does not do

§B2 below says the runner **skips** the four negatives under Branch B "with the reason printed".
Measured: **`cli.py run --via sql` raises instead of skipping.** It calls `envelope.enforce` on
every question including the negatives; `N01` names `mainline_qa`, which the envelope refuses
outright, and `QaSchemaRefused` propagates out of the runner. The behaviour B2 specifies is the
correct one; the code does not implement it. Recorded in `evidence/deploy/judge-run.json` and in
`JUDGE-PACK.md` §8 rather than patched here, because `cli.py` belongs to the agents-mcp domain.

A companion finding, same artefact: **`cli.py run --via mcp` cannot reach the live surface
either.** `mainline_mcp.client.ToolDialect` sends the statement as `statement=` and omits
`database=`; the live server requires `query=` and makes `database` mandatory. The session, the
auth and the cluster pin all work — the argument names do not.

---

## The rule that does not change under any branch

**No key is ever published on the demo cluster.** Not a weaker one; none.

The original justification for this rule was that the Managed MCP write surface is insert-only
and bound to `mainline_meas.external_attestation` — that insert-only is still real, and a real
write surface on the cluster the film was shot against is not something a published credential
should reach. **§0.3 shows that justification was wrong in both particulars, and the measured
truth is worse:** the surface is not insert-only, it is `create_database` / `create_table` /
`insert_rows` at *account* scope, and it is not bound to anything. The rule survives its own
reasoning being corrected, which is the outcome you want from a rule written in advance.

The text below refers throughout to `mainline-verify`, a separate throwaway cluster restored
from the demo cluster, holding synthetic data only. **§0.2: it does not exist.** One cluster,
`mainline-dev`, synthetic in full, and the published login is read-only against fourteen views.

## Branch A — the key can be published

*Not in force. Retained as written.*

The pack runs as written. A judge adds the endpoint to their own MCP client and asks the
sixteen questions in [`PACK.md`](PACK.md). None of our code sits between the prompt and the row.

```bash
python verticals/mainline/demo/judge/cli.py run --via mcp
```

## Branch B — the key cannot be published

**IN FORCE since 2026-08-11.** Three substitutes, in the order they should be believed. **None of
them is presented as equal to Branch A**, and the difference is stated rather than absorbed.

### B1 · The same statements, on the judge's own cluster (unchanged strength)

*This is the degrade that shipped.* Two forms of it, and the second is the one the submission
publishes.

**On the judge's own node.** Every positive question in the pack runs over pgwire against a local
single-node CockroachDB the judge started themselves, seeded from the committed fixtures:

```bash
just corpus:up && just corpus:seed
export TRAPPOINT_DSN=postgresql://root@localhost:26257/mainline?sslmode=disable
python verticals/mainline/demo/judge/cli.py run --via sql
```

**On ours, read-only.** The published credential is the `mainline_judge` login against
`mainline_demo` on the live cluster — fourteen `mainline_audit` views, no base table, no write,
no DDL. Verified from the other side on 2026-08-11: **14 of 14 views readable, 6 non-empty; 11 of
11 statements refused at `42501`**. The connection line and the five-minute walkthrough are
[`JUDGE-PACK.md`](../../../../docs/deploy/JUDGE-PACK.md) §0.2 and §2.4; the credential itself is
in the submission form and in no file in this repository.

This checks everything about the **questions** that Branch A checks: that each parses, that
every column exists, that the plan really shows a vector search on a named index with a
non-empty prefix span, and that the result fits the budget. On the judge's own node it is in one
respect *stronger* than Branch A, because the judge controls the cluster and the data is theirs
to inspect.

What neither form carries is the sentence Branch A carries: *asked over CockroachDB's own
public managed endpoint, with none of our code in the path.* That sentence is about the
transport, and no local run can supply it.

**Measured cost of the degrade, so it is not a hand-wave:** over the sixteen questions,
**15 of 16 behaved as expected over Managed MCP; 12 of 16 over pgwire as `mainline_judge`.** The
four that differ are `Q10`/`Q10C` (plan proofs — they read a base table, and the judge login holds
`SELECT` on no base relation anywhere; the `42501` **is** the grant working) and `N03`/`N04`
(below).

### B2 · The negatives do not survive this branch, and we say so

The four negatives are marked `mcp_only` in the pack and the runner is specified to **skip** them
here, with the reason printed:

> over a pgwire connection as cluster admin this statement SUCCEEDS. Running it here and
> reporting a pass would invert its meaning.

**§0.4: `cli.py run --via sql` raises instead of skipping.** The specification above is right and
the implementation is not; the finding is recorded rather than the spec relaxed.

`crdb_internal` is unreachable *over the Managed MCP surface*. It is perfectly reachable
over SQL as an admin, and the bypass beat of the film exists precisely to show what a cluster
administrator can in fact do. A run that reported these as passing would be claiming a
property of the wrong transport.

Measured, and this is the whole reason the transport distinction matters:

| | over Managed MCP | over pgwire as `mainline_judge` |
|---|---|---|
| `N01` `mainline_qa` | **FAILS — readable.** A real gap; `GRANTS.yaml` S14 says no automated account on any tier reaches it | passes — `42501`, no `USAGE` |
| `N02` `crdb_internal` | passes — server blocklist | passes — `42501` |
| `N03` `pg_catalog` | passes — server blocklist | **fails — readable by any login**, 654 rows |
| `N04` `information_schema` | passes — server blocklist | **fails — readable by any login**, 446 rows |

`N03` and `N04` fail over SQL because `pg_catalog` and `information_schema` are per-user-filtered
catalogues every client needs to introspect at all — independently reproduced on a local
CockroachDB v26.2.5 node on 2026-08-13, where a view-only role read 372 and 340 rows out of them.
That is not a hole in the grant; it is the wrong transport for the claim.

`N01` is different, and it is the one finding on this page that is a fault in **us** rather than
in the branch: the envelope's claim is wider than the measurement supports. It is recorded under
`divergences` in `evidence/deploy/judge-run.json` with `by_design: false`, not narrowed.

Their server-side half stays in `tests/integration/mcp/test_negative_reachability.py`, which
skips with a reason and never passes when no key is present. Under Branch B those assertions
are **unrun**, not green, and the submission says "unrun" — see
[`../DEMO-HONESTY.md`](../DEMO-HONESTY.md) §4.

### B3 · A recorded session, labelled as a recording

The film's beat 5 becomes a recorded Managed-MCP session against the demo cluster, captured
before submission, with the round trips written to `evidence/demo-run-<ts>/mcp/` and hashed
into the custody ledger. A recording is evidence that a session occurred; it is not
something a stranger can re-run, and the on-screen label says which of the two it is.

Alongside it, our own read-only aggregate endpoints serve the same `mainline_audit` views
over HTTP. That path has our code in it, which is the whole difference, and the honesty card
prints the difference rather than the claim.

**Status:** B1 is what shipped and is sufficient on its own — a judge reads the live ledger with
none of our code in the path, over pgwire. B3 is not required for that claim and is not asserted
as done.

## What changes in each artefact, and who changes it

| Artefact | Under Branch B |
|---|---|
| `PACK.md` | unchanged — the questions are the questions. `run --via sql` is the invocation |
| `demo/VERIFY.md` | its Tier-3 section states the degrade; that file's owner makes the edit, not this pack |
| `demo/honesty/card.html` | generated; the MCP row reads "recorded session" because the attestation says so |
| `tests/integration/mcp/` | skips with a reason. Skipped is reported as skipped, never as passed |
| the submission text | says "over our own read-only endpoints plus a recorded managed session", never "over CockroachDB's endpoint" |
| [`MCP-CONFIG.md`](MCP-CONFIG.md) | **added under Branch B**: the client configuration is published even though the key is not, so the claim "we use the Managed MCP Server" arrives with the wiring that reproduces it |

## The trigger, and who pulls it

The branch is chosen by the **G1 ground-truth attestation's GT-17 entry**, not by a
judgement call on the day. When that entry records that key publication is outside terms,
Branch B is in force from that moment and the artefacts above are updated in the same
change. An unanswered GT-17 counts as a failed one: the fallback executes and the question
becomes a standing nightly assertion the same day.

**What actually happened is a third case the trigger did not enumerate**, and it is recorded
rather than back-fitted: GT-17 came back *permitted and available*, and Branch B was taken anyway
because the only credential that reaches the endpoint is an account-scoped key with DDL. The
trigger's spirit — "an unanswered question is a failed one, degrade" — held; its letter did not
cover the case. §0 is the amendment.

## What is never claimed under either branch

- That a run of this pack proves the retrieval was exhaustive. It is exhaustive over the
  retrieval that ran, and the difference is the whole honesty of the mechanism.
- That an approximate-nearest-neighbour result replays bit for bit. What is claimed is
  replayability of the arithmetic and of the disclosed boundary.
- That the audit views are site-scoped by the MCP identity. Which SQL identity the managed
  endpoint runs as was day-1 check GT-10; **answered 2026-08-11 — it is `managed-mcp`, not
  `root`** — but the views are still built to be safe when read in full, and MCP is never
  marketed as site-scoped.
- That the published login can write anything. **It cannot.** §0.3.
- That the cluster is in Australia. The database is in Singapore and Bedrock inference is in
  Sydney. Any claim of end-to-end Australian data residency is false for this deployment and
  appears nowhere.
