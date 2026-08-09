<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
-->

# The ops views are the API — because `crdb_internal` is unreachable

## The limitation, stated plainly

The CockroachDB Managed MCP Server cannot reach `system`, `crdb_internal`, `pg_catalog`,
`information_schema` or `pg_extension`. Not "should not"; cannot. The tools refuse.

Most CockroachDB operational knowledge — the published skills, the blog posts, the DB
Console pages, the runbooks an experienced operator already has — reads exactly those
schemas. `crdb_internal.cluster_queries`, `crdb_internal.node_statement_statistics`,
`crdb_internal.index_usage_statistics`, `crdb_internal.jobs`: none of them exist for an
agent on this surface.

So the stock CockroachDB Agent Skills that the Steward consumes **cannot execute their own
diagnostics here**, and no amount of prompting changes that. The Steward reads
pre-materialised `mainline_audit` views instead.

## Why this is the design and not a workaround

An operator-facing question that has nowhere to go except a view somebody wrote is a
question with a versioned, budgeted, reviewable answer. `crdb_internal` has none of those
properties: it is a moving target across versions, it is unbounded in size, and a query
against it is a query nobody has ever reviewed.

Every view below is declared in `spec/mcp/audit-surface.contract.yaml` with its columns,
its row cap and its byte budget; the data-model lead implements it as DDL; the budget
prober measures it nightly and fails at 8 KiB — 80 % of the server's 10 KiB response cap,
so the alarm fires with headroom rather than in front of an auditor.

**The platform's limitation, taken seriously, is the product's ops API.** That is the same
move the whole system makes: the MCP response cap forces the audit surface to be
aggregate-first, which was the correct shape anyway.

## The four ops views

### `v_gate_latency_daily` — `site_id, d, p50_ms, p95_ms, p99_ms, n`

The gate transaction's latency by day. The p95 is the product's SLO.

**Cannot tell you** which statement was slow, or why. There are no statement fingerprints
on this surface. If the p95 moves and you need the cause, that investigation happens over
pgwire with a human, not here.

### `v_txn_restart_daily` — `site_id, d, restarts, txns, restart_ratio`

Serializable restart counts by day. Restarts are normal under `SERIALIZABLE`; a *rising*
ratio is the signal, and the view carries `txns` beside `restarts` so a rise driven by
volume can be told apart from a rise driven by contention.

**Cannot tell you** which two transactions conflicted.

### `v_unused_indexes` — `table_name, index_name, last_read, total_reads`

Indexes with no reads in the window.

**Read this one with care.** The three vector indexes — `clause_embedding@ce_ann`,
`event_cue_embedding@cue_scoped_idx`, `event_cue_coarse@cue_sweep_idx` — are not
droppable on an ops recommendation. Creating a vector index on a non-empty table blocks
writes; `IMPORT INTO` is unsupported on a vector-indexed table and the documented remedy
is import-then-index; and the bulk path is fenced behind a circuit breaker for exactly
that reason. An appearance here is an observation for a human, never an action.

**Cannot tell you** whether an index is used by a plan that has not run yet. Window
absence is not evidence of uselessness.

### `v_changefeed_health` — `feed_name, status, high_water_lag_s, last_error_at`

Liveness and lag for `cf_outbox`, `cf_custody` and `cf_bulk`.

The failure to look hardest for is **a feed whose status reads healthy and whose
high-water mark is not advancing.** Setting `Flush.Messages` without `Flush.Frequency`
implies infinite frequency and batches sit indefinitely — a silent, total custody stall
that looks exactly like "nothing is happening". `high_water_lag_s` is the only column that
distinguishes the two, which is why the view carries it.

**Cannot tell you** the job's internal error history; `crdb_internal.jobs` is unreachable.

## The five evidentiary views the Steward also reads

`v_ledger_health`, `v_fixity_coverage`, `v_agent_actions`,
`v_weakenings_without_disposition` and `v_disposition_coverage` are the auditor's views,
not the Steward's, and the Steward reads them for a different reason: an ops review that
ignored open witness debt or an undispositioned weakening would be an ops review of the
wrong system.

Two of them carry `ancestry_complete`. **Where a view carries a completeness flag, the
narrative must report it.** The counts under a `false` are lower bounds, and reporting a
lower bound as a total is precisely the misstatement the flag exists to prevent.

`v_blame_coverage` reports `truncated_closures` as a **count**, and
`v_recall_conservation` reports `any_degraded` as an **inverted boolean**. Neither is
declared as a truncation flag in the contract, because declaring them would make the
prober read them backwards. That is a real gap in the surface and it is written down here
rather than papered over.

## What no view on this surface can do

`mainline_qa` — per-named-person deliberation measurement — receives no MCP account on any
tier, ever (S14). It is unreachable by policy, not by accident, and the negative
reachability suite asserts the server refuses it rather than trusting our client to.
