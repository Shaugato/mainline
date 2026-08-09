-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- MAINLINE · 0167_v_unused_indexes.sql
-- CREATE VIEW mainline_audit.v_unused_indexes — the ops family, arm 3 of 4
--
-- MI: MI22
-- I: I06
-- COUNSEL-GATED: no
-- RATIONALE: An index nobody traverses is usually a cost finding. On the recall path it is
--            something else entirely: the platform ground truth (F1) measured that at 5 200
--            rows an UNHINTED prefix-constrained ANN query does not use the vector index at
--            all — the plan is top-k, render, filter, scan. So a vector index sitting at zero
--            reads is the signature of an arm that stopped naming its index, and the recall
--            channel has silently become brute force with extra steps. That is why this view
--            carries `is_vector` and sorts it first.
--
-- migration:  0167_v_unused_indexes
-- domain:     datamodel / dm-views-rls
-- band:       0155-0169z · datamodel/dm-views-rls · AUTHORED (migrations.allocation.toml, MR-6 lock 1)
-- statements: 1
-- invariants: MI22 — the gate fails closed on a stale or absent projection. `snapshot_age`
--                    is what makes a stale snapshot legible as stale.
--             I06  — a dependency a gate consumes is COMPUTED, never declared: "is this
--                    index being traversed" is measured, never asserted.
-- source:     ARCHITECTURE.md §17 (the ops family) · §9.1 job 2 (index-truth assertion) ·
--             §9.2 (three vector indexes, one per table) · §4.1 laws 6 and 12 ·
--             docs/leads/datamodel.md PLATFORM GROUND TRUTH F1
-- requires:   0155 mainline_ops.index_usage_snapshot
-- sqlstate:   none — this object refuses nothing.
-- forward-only; no .down.sql exists at or below the protected floor.
--
-- ─────────────────────────────────────────────────────────────────────────────
-- WHY THIS READS A SNAPSHOT TABLE AND NOT crdb_internal
-- ─────────────────────────────────────────────────────────────────────────────
-- §4.1 law 12 forbids the Managed-MCP identity every system catalog, including
-- `crdb_internal.index_usage_statistics`, which is where this data actually
-- lives. The catalog read therefore happens on pgwire, under a privileged
-- collector, and lands in `mainline_ops.index_usage_snapshot` (migration 0155)
-- as a dated, attributable row. This view is a projection of the newest snapshot
-- per object and reads no catalog at all — which is the property
-- `tests/integration/schema/test_mi_views.py` asserts for every view in this
-- band by scanning the SQL text.
--
-- ─────────────────────────────────────────────────────────────────────────────
-- "NEWEST SNAPSHOT" IS PER OBJECT, NOT PER RUN, AND THAT MATTERS
-- ─────────────────────────────────────────────────────────────────────────────
-- A collector that fails halfway leaves a run in which half the objects were
-- recorded. Taking `max(collected_at)` across the whole table and filtering to
-- it would then silently drop every object the failed run never reached — the
-- indexes would VANISH from the report rather than appear as stale, and a
-- vanished index reads as a resolved finding.
--
-- So the newest row is taken per (schema, table, index) via a correlated
-- max(collected_at), and `snapshot_age` is reported beside it. An object whose
-- newest snapshot is three days old is present, visible, and obviously stale.
--
-- ─────────────────────────────────────────────────────────────────────────────
-- WHAT THIS VIEW IS NOT
-- ─────────────────────────────────────────────────────────────────────────────
-- 1. IT IS NOT PERMISSION TO DROP AN INDEX. A partial UNIQUE index enforcing
--    `one_live_disposition` (MI08) has zero READS by construction — it is a
--    constraint, and constraints are checked on write. `is_unique` is carried so
--    that this view cannot be read as a drop list without the reader seeing that
--    column, and no automation in this repository acts on it.
-- 2. IT IS NOT THE INDEX-TRUTH ASSERTION. That is §9.1 job 2: `explain_query`
--    over the public Managed-MCP endpoint against a generated recall arm,
--    asserting the EXPLAIN fragment names the HINTED index (F1 — an unhinted
--    assertion fails at demo corpus scale). A usage counter cannot substitute
--    for a plan assertion, and claiming it could would be claiming a mechanism
--    this file does not contain.

CREATE VIEW mainline_audit.v_unused_indexes AS
  WITH latest AS (
    SELECT s.schema_name      AS schema_name,
           s.table_name       AS table_name,
           s.index_name       AS index_name,
           s.index_kind       AS index_kind,
           s.total_reads      AS total_reads,
           s.window_reads     AS window_reads,
           s.last_read_at     AS last_read_at,
           s.counters_reset   AS counters_reset,
           s.index_created_at AS index_created_at,
           s.collected_at     AS collected_at,
           s.collector        AS collector
      FROM mainline_ops.index_usage_snapshot s
     WHERE s.collected_at = (
             SELECT max(s2.collected_at)
               FROM mainline_ops.index_usage_snapshot s2
              WHERE s2.schema_name = s.schema_name
                AND s2.table_name  = s.table_name
                AND s2.index_name  = s.index_name)
  ),
  t AS (SELECT count(*) AS group_count FROM latest WHERE total_reads = 0)
  SELECT latest.schema_name                       AS schema_name,
         latest.table_name                        AS table_name,
         latest.index_name                        AS index_name,
         latest.index_kind                        AS index_kind,
         (latest.index_kind = 'vector')           AS is_vector,
         (latest.index_kind = 'unique')           AS is_unique,
         latest.total_reads                       AS total_reads,
         latest.window_reads                      AS window_reads,
         latest.last_read_at                      AS last_read_at,
         latest.index_created_at                  AS index_created_at,
         latest.collected_at                      AS collected_at,
         latest.collector                         AS collector,
         -- Stale-snapshot legibility. An ops finding computed from a three-day-old
         -- measurement is a three-day-old finding, and MI22's whole content is that a
         -- stale projection must present as stale rather than as current.
         (now() - latest.collected_at)            AS snapshot_age,
         (latest.collected_at > now() - INTERVAL '2 days') AS snapshot_fresh,
         -- A counter reset makes "zero reads" meaningless: the index may have been
         -- traversed a million times before the node restarted. Fail-closed — a group
         -- whose counters reset reports its measurement as incomplete.
         (NOT latest.counters_reset)              AS measurement_complete,
         t.group_count                            AS group_count,
         (t.group_count <= 25)                    AS rows_complete
    FROM latest CROSS JOIN t
   WHERE latest.total_reads = 0
   ORDER BY (latest.index_kind = 'vector') DESC,
            latest.schema_name, latest.table_name, latest.index_name
   LIMIT 25;
