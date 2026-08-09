<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
-->

# Observability — nightly

Staged skills: `triaging-live-sql-activity`, `profiling-statement-fingerprints`,
`monitoring-background-jobs`. Read them for *method* — how to read a latency
distribution, what a restart ratio means, how a job stalls — and ignore every instruction
in them that reaches for `crdb_internal`, which you cannot reach.

## What tonight's review is for

The gate transaction is the product. It is one `SERIALIZABLE` transaction that materialises
blocking checks, issues an exposure receipt, and refuses a merge when a recalled precursor
has no signed disposition. Two numbers say whether it is well: **how long it takes** and
**how often it restarts**. A third — changefeed health — says whether the custody path is
moving at all.

## Read, in this order

1. **`v_gate_latency_daily`** — p50, p95, p99 and `n` per site per day. The p95 is the
   product's own SLO. Report the trend across the days present, not just the last row: a
   single night's p95 is noise, and three nights of drift is a fact.

2. **`v_txn_restart_daily`** — `restarts`, `txns`, `restart_ratio`. Serializable restarts
   are normal and a *rising* ratio is not. Note whether the rise tracks volume (`txns`) or
   is independent of it; those are different problems and the view can tell them apart.

3. **`v_changefeed_health`** — `feed_name`, `status`, `high_water_lag_s`, `last_error_at`.
   Three feeds matter: `cf_outbox`, `cf_custody`, `cf_bulk`. The failure to look hardest
   for is a feed whose status reads healthy and whose high-water lag is not advancing —
   that is what a batching stall looks like from the outside, and it is indistinguishable
   from "nothing is happening" unless somebody reads the lag.

4. **`v_ledger_health`** — `tree_size`, admissible and inadmissible checkpoints, and
   `open_debt`. Open witness debt is not an error: an unreachable witness produces a debt
   row and never a blocked merge. **Ageing** debt is the observation — report the number
   and whether it is growing.

## What to say in the narrative

For each view: what the numbers were, what moved, and what a reader should look at next.
Where a view returned no rows, say so plainly — a night with no data and a night with good
data are different, and only one of them is good news.
