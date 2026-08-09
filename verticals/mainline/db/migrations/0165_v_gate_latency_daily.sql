-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- MAINLINE · 0165_v_gate_latency_daily.sql
-- CREATE VIEW mainline_audit.v_gate_latency_daily — the ops family, arm 1 of 4
--
-- MI: MI22
-- I: I14
-- COUNSEL-GATED: no
-- RATIONALE: The gate transaction's p99 is a product requirement — it is the stated reason
--            the blame closure is materialised at all rather than walked in a trigger. A
--            latency surface that the Steward's stock skills can read WITHOUT crdb_internal
--            is therefore not an ops nicety; it is how the justification for the schema's
--            central design decision stays checkable after the decision is made.
--
-- migration:  0165_v_gate_latency_daily
-- domain:     datamodel / dm-views-rls
-- band:       0155-0169z · datamodel/dm-views-rls · AUTHORED (migrations.allocation.toml, MR-6 lock 1)
-- statements: 1
-- invariants: MI22 — the gate fails closed on a stale or absent projection. A gate that has
--                    stopped transacting produces no rows here, and `rows_complete` plus an
--                    empty result is how "the gate is not running" reads.
--             I14  — minimal refusal: every refusal emits an irreducible reason set. The
--                    refusal counts here are grouped by the SQLSTATE class that carries it.
-- source:     ARCHITECTURE.md §17 (the ops family) · §9.4 (stock skills pointed at
--             pre-materialised ops views because crdb_internal is unreachable) ·
--             §5.7 (agent_action DDL) · §12 (Class A operational telemetry) · §4.1 law 12
-- requires:   0089 mainline_meas.agent_action
-- sqlstate:   none — this object refuses nothing.
-- forward-only; no .down.sql exists at or below the protected floor.
--
-- ─────────────────────────────────────────────────────────────────────────────
-- WHERE THE NUMBERS COME FROM, AND WHY NOT FROM crdb_internal
-- ─────────────────────────────────────────────────────────────────────────────
-- §4.1 law 12: the Managed MCP has NO ACCESS to `system`, `crdb_internal`,
-- `pg_catalog`, `information_schema` or `pg_extension`. Every stock CockroachDB
-- observability skill reads `crdb_internal.node_statement_statistics` or
-- similar, so none of them runs against this surface. §9.4's answer is to point
-- them at pre-materialised ops views, and this is one.
--
-- The source is `mainline_meas.agent_action`, which the fleet already writes for
-- every action on every transport: `agent_role`, `tool`, `latency_ms`,
-- `sqlstate`, `outcome`, `at`. Filtering to `agent_role = 'agent_gate'` and
-- `transport = 'pgwire'` isolates the gate's own transactions. Nothing is
-- inferred and nothing is sampled — §12 says Class B evidentiary telemetry is
-- NEVER sampled, and although latency is Class A, it is recorded on the same
-- rows, so the population here is complete by construction.
--
-- ─────────────────────────────────────────────────────────────────────────────
-- WHY THRESHOLD COUNTS AND NOT PERCENTILES
-- ─────────────────────────────────────────────────────────────────────────────
-- Two reasons, and the second is the one that decided it.
--
-- 1. An SLO is a threshold, not a quantile. "99 % of gate transactions complete
--    within 1 s" is answered exactly by `over_1000ms / n`, and answered only
--    approximately by a p99 over a day's rows.
--
-- 2. This file will not take a dependency on ordered-set aggregate support
--    (`percentile_cont(…) WITHIN GROUP (ORDER BY …)`) that has not been verified
--    on the target cluster. The platform ground truth in docs/leads/datamodel.md
--    lists what WAS measured on v26.2.5; ordered-set aggregates are not on it.
--    An unverified function inside a migration is a migration that fails on a
--    fresh cluster and nowhere else, which is the DM-16 failure mode in a
--    different costume. count/avg/max/min are unambiguous and universal.
--
-- The thresholds are fixed literals rather than a parameter table because a view
-- takes no arguments and a lookup would be a join whose absence would change the
-- row count. Moving an SLO is a migration, which is the correct weight for it.
--
-- ─────────────────────────────────────────────────────────────────────────────
-- WHAT THIS VIEW IS NOT
-- ─────────────────────────────────────────────────────────────────────────────
-- IT IS NOT A CLUSTER LATENCY VIEW. It reports the latency the GATE observed and
-- recorded, which includes application time and excludes anything the gate never
-- ran. A slow cluster with a stopped gate looks healthy here and is not, which is
-- why `v_changefeed_health` and `v_txn_restart_daily` sit beside it.

CREATE VIEW mainline_audit.v_gate_latency_daily AS
  WITH g AS (
    SELECT date_trunc('day', a.at)                AS d,
           a.tool                                 AS tool,
           count(*)                               AS n,
           count(*) FILTER (WHERE a.outcome = 'ok')       AS ok,
           count(*) FILTER (WHERE a.outcome = 'refused')  AS refused,
           count(*) FILTER (WHERE a.outcome = 'error')    AS errored,
           count(*) FILTER (WHERE a.outcome = 'abstained') AS abstained,
           min(a.latency_ms)                      AS min_ms,
           round(avg(a.latency_ms)::NUMERIC, 1)   AS mean_ms,
           max(a.latency_ms)                      AS max_ms,
           count(*) FILTER (WHERE a.latency_ms > 250)  AS over_250ms,
           count(*) FILTER (WHERE a.latency_ms > 1000) AS over_1000ms,
           count(*) FILTER (WHERE a.latency_ms > 5000) AS over_5000ms,
           count(*) FILTER (WHERE a.latency_ms IS NULL) AS unmeasured
      FROM mainline_meas.agent_action a
     WHERE a.agent_role = 'agent_gate'
       AND a.transport  = 'pgwire'
       AND a.at > now() - INTERVAL '21 days'
     GROUP BY date_trunc('day', a.at), a.tool
  ),
  t AS (SELECT count(*) AS group_count FROM g)
  SELECT g.d           AS d,
         g.tool        AS tool,
         g.n           AS n,
         g.ok          AS ok,
         g.refused     AS refused,
         g.errored     AS errored,
         g.abstained   AS abstained,
         g.min_ms      AS min_ms,
         g.mean_ms     AS mean_ms,
         g.max_ms      AS max_ms,
         g.over_250ms  AS over_250ms,
         g.over_1000ms AS over_1000ms,
         g.over_5000ms AS over_5000ms,
         g.unmeasured  AS unmeasured,
         -- Fail-closed completeness: a group in which some action recorded no latency is a
         -- group whose distribution is missing rows, and the reader must be told rather
         -- than shown a mean over the subset that happened to be instrumented.
         (g.unmeasured = 0) AS measurement_complete,
         t.group_count      AS group_count,
         (t.group_count <= 25) AS rows_complete
    FROM g CROSS JOIN t
   ORDER BY g.d DESC, g.tool
   LIMIT 25;
