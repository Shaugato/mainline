-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- MAINLINE · 0155_ops_index_usage_snapshot.sql
-- CREATE TABLE mainline_ops.index_usage_snapshot — the only place index truth can live
--
-- MI: MI22
-- I: I06
-- COUNSEL-GATED: no
-- RATIONALE: The Managed MCP identity may not read crdb_internal, pg_catalog,
--            information_schema, pg_extension or system (§4.1 law 12), so an ops view over
--            index usage has no catalog to read. Rather than drop the view or lie about
--            where its numbers come from, the catalog read moves to a privileged collector
--            on pgwire and the result lands here as a dated, attributable row. The
--            limitation becomes the product's ops API, which is the same move §9.4 makes for
--            the whole Agent Skills fleet.
--
-- migration:  0155_ops_index_usage_snapshot
-- domain:     datamodel / dm-views-rls
-- band:       0155-0169z · datamodel/dm-views-rls · AUTHORED, allocated by
--             verticals/mainline/db/migrations.allocation.toml (MR-6 lock 1). The band's
--             declared contents are the mainline_audit views; this table is the DM-16
--             minimal addition those views require, placed at the head of the band so that
--             it precedes every reader of it.
-- statements: 1
-- invariants: MI22 — the gate fails closed on a stale or absent projection. Applied to an ops
--                    surface: `collected_at` is on every row, so a stale snapshot is visible
--                    as stale rather than presented as current.
--             I06  — a dependency a gate consumes is COMPUTED, never declared. This table is
--                    the computed side of "which indexes are actually being traversed".
-- source:     ARCHITECTURE.md §17 (the ops family: v_unused_indexes) · §9.1 (MCP limits) ·
--             §9.4 (stock skills pointed at pre-materialised ops views) · §4.1 law 12
--             docs/leads/datamodel.md DM-10 (named constraints), DM-16 (missing objects are
--             added minimally rather than left dangling)
-- requires:   0005 CREATE SCHEMA mainline_ops
-- sqlstate:   23514 on the named CHECKs; this table gates nothing.
-- forward-only; no .down.sql exists at or below the protected floor.
--
-- ─────────────────────────────────────────────────────────────────────────────
-- WHY THIS TABLE EXISTS AND WHO IS ALLOWED TO WRITE IT
-- ─────────────────────────────────────────────────────────────────────────────
-- §17 names four ops views — v_gate_latency_daily, v_txn_restart_daily,
-- v_unused_indexes, v_changefeed_health — "the ops family the Steward's stock
-- skills read instead of crdb_internal". Two of those four are derivable from
-- tables MAINLINE already keeps: gate latency and transaction restarts are in
-- mainline_meas.agent_action, which records agent_role, latency_ms, sqlstate and
-- outcome for every action on every transport. The other two are not derivable
-- from anything in §5, and §5 never defined a source for them. That is exactly
-- the DM-16 case: an object the audit surface references that the DDL never
-- created is a migration that fails on a fresh cluster and nowhere else.
--
-- The writer is the ops collector — a scheduled task holding pgwire credentials
-- and READ access to crdb_internal.index_usage_statistics — never the MCP
-- identity, which by construction cannot see the catalog this table paraphrases.
-- The collector role is a deployment concern and lives in infra/, exactly as the
-- IdP sync that writes mainline.person does; no application role in GRANTS.yaml
-- writes here.
--
-- ─────────────────────────────────────────────────────────────────────────────
-- WHAT THIS TABLE IS NOT
-- ─────────────────────────────────────────────────────────────────────────────
-- 1. IT IS NOT EVIDENCE. It is Class A operational telemetry (§12), not Class B.
--    Losing it is annoying, not spoliation. It carries no ledger entry and it is
--    not append-only-enforced, because a paraphrase of a mutable counter is not
--    a business record and pretending otherwise would dilute the tables that are.
--
-- 2. IT IS NOT THE INDEX-TRUTH ASSERTION. That is §9.1 job 2 — `explain_query`
--    over the public Managed-MCP endpoint against a generated recall arm,
--    asserting the EXPLAIN fragment names the hinted vector index. This table
--    answers "which indexes has nobody traversed since the last snapshot", which
--    is a cost question. Confusing the two would let a cost report stand in for
--    a correctness proof.
--
-- 3. IT IS NOT A SUBSTITUTE FOR `recall_certificate.index_fingerprint`. INSPECT
--    skips vector indexes, so the fingerprint is the only structural tripwire on
--    the recall path; a usage counter says nothing about whether the index still
--    contains what it claimed to.

CREATE TABLE mainline_ops.index_usage_snapshot (
  snapshot_id     UUID        NOT NULL DEFAULT gen_random_uuid(),
  collected_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  -- The collector's own identity, so a snapshot is attributable to the task that took it.
  -- A row whose collector cannot be named is a row nobody can re-run.
  collector       STRING      NOT NULL,
  collector_ver   STRING      NOT NULL,
  -- The object, spelled out rather than joined: this table exists precisely BECAUSE the
  -- reader may not reach the catalog, so a foreign key into the catalog would be useless
  -- to it and a foreign key into `mainline.*` would be a lie about what an index is.
  schema_name     STRING      NOT NULL,
  table_name      STRING      NOT NULL,
  index_name      STRING      NOT NULL,
  index_kind      STRING      NOT NULL,
  -- The measurement. `total_reads` is cumulative since the counters last reset, which is
  -- why `window_reads` is carried separately: a cumulative counter that resets on a node
  -- restart looks exactly like an index that stopped being used.
  total_reads     INT8        NOT NULL,
  window_reads    INT8        NOT NULL,
  last_read_at    TIMESTAMPTZ NULL,
  counters_reset  BOOL        NOT NULL DEFAULT false,
  index_created_at TIMESTAMPTZ NULL,

  CONSTRAINT pk_index_usage_snapshot PRIMARY KEY (snapshot_id),
  CONSTRAINT index_usage_one_per_object_per_run
    UNIQUE (collected_at, schema_name, table_name, index_name),
  CONSTRAINT index_usage_collector_stated  CHECK (collector <> ''),
  CONSTRAINT index_usage_collector_ver_stated CHECK (collector_ver <> ''),
  CONSTRAINT index_usage_schema_stated     CHECK (schema_name <> ''),
  CONSTRAINT index_usage_table_stated      CHECK (table_name <> ''),
  CONSTRAINT index_usage_index_stated      CHECK (index_name <> ''),
  CONSTRAINT index_usage_kind_known
    CHECK (index_kind IN ('primary', 'secondary', 'inverted', 'vector', 'partial', 'unique')),
  CONSTRAINT index_usage_reads_nonneg      CHECK (total_reads >= 0 AND window_reads >= 0),
  -- A window that exceeds the cumulative total is arithmetically impossible unless the
  -- counters reset between snapshots, so the row must say so. An impossible pair that
  -- nobody refuses is how a cost report starts quietly lying.
  CONSTRAINT index_usage_window_within_total
    CHECK (counters_reset = true OR window_reads <= total_reads),
  INDEX index_usage_by_time (collected_at DESC, schema_name, table_name)
);
