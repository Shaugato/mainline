-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- MAINLINE · 0166_v_txn_restart_daily.sql
-- CREATE VIEW mainline_audit.v_txn_restart_daily — the ops family, arm 2 of 4
--
-- MI: MI22
-- I: I14
-- COUNSEL-GATED: no
-- RATIONALE: `40001` is the ONLY retryable SQLSTATE in this system, and everything else in
--            the 40xxx/23xxx/P0001 space is a refusal that must never be retried. A view that
--            separates the two is therefore not an ops convenience: it is the surface on which
--            "the application is retrying a refusal" becomes visible, and retrying a refusal
--            is how a gate gets talked past by a client library rather than by a person.
--
-- migration:  0166_v_txn_restart_daily
-- domain:     datamodel / dm-views-rls
-- band:       0155-0169z · datamodel/dm-views-rls · AUTHORED (migrations.allocation.toml, MR-6 lock 1)
-- statements: 1
-- invariants: MI22 — the gate fails closed on a stale or absent projection; contention that
--                    never resolves is one way a projection goes stale.
--             I14  — minimal refusal. The refusal classes are enumerated here so that an
--                    unmodelled one cannot hide inside "errors".
-- source:     ARCHITECTURE.md §17 (the ops family) · §16 ("40001 is the only retryable
--             code") · §9.4 · §5.7 (agent_action DDL) · §4.1 law 12
-- requires:   0089 mainline_meas.agent_action
-- sqlstate:   none — this object refuses nothing.
-- forward-only; no .down.sql exists at or below the protected floor.
--
-- ─────────────────────────────────────────────────────────────────────────────
-- WHY SERIALIZABLE CONTENTION IS A FIRST-CLASS OPS METRIC HERE
-- ─────────────────────────────────────────────────────────────────────────────
-- MAINLINE runs SERIALIZABLE by default and asserts it nightly, because one
-- `SET default_transaction_isolation` would otherwise silently unweld every
-- gate. The cost of that choice is retryable serialization failures under
-- contention, and the design accepts it: §9.5 notes that the MATERIALISED
-- conflict means the gate survives even if the isolation level is tampered with.
--
-- What the design does NOT accept is contention that is invisible. A rising
-- `restarts` count on one tool is the signature of two agents converging on the
-- same permit row, which under the projection idiom means two writers racing to
-- maintain the same counter. That is a schema-level finding, not a capacity one,
-- and it is only findable if the number is reported per tool per day.
--
-- ─────────────────────────────────────────────────────────────────────────────
-- THE COLUMN THAT MATTERS MOST IS `unmodelled`
-- ─────────────────────────────────────────────────────────────────────────────
-- §16: any SQLSTATE outside {40001, 23514, 23503, 23505, P0001} means the
-- database refused for a reason nobody modelled, and the conformance suite fails
-- on it by design. In production there is no suite — there is this column. A
-- non-zero `unmodelled` is a defect report the system wrote about itself, and it
-- should be read before any latency number on the surface.
--
-- `42501` is broken out separately from `unmodelled` for one reason: it is the
-- expected code when an RLS write policy is missing (S22, case CF-22). A cluster
-- restored without `grants apply`, or with a policy dropped, produces exactly
-- this signature — a wall of 42501 on one role — and calling that "unmodelled"
-- would bury the most diagnosable failure this deployment has.
--
-- ─────────────────────────────────────────────────────────────────────────────
-- WHAT THIS VIEW IS NOT
-- ─────────────────────────────────────────────────────────────────────────────
-- IT IS NOT A COUNT OF CLUSTER-SIDE TRANSACTION RESTARTS. The cluster's own
-- counter lives in `crdb_internal`, which this surface may not read (§4.1
-- law 12). This is the count of restarts the APPLICATION observed and recorded.
-- The two differ whenever a restart is absorbed by a driver's retry loop without
-- reaching our instrumentation, so this number is a LOWER BOUND and must be
-- described as one.

CREATE VIEW mainline_audit.v_txn_restart_daily AS
  WITH g AS (
    SELECT date_trunc('day', a.at)   AS d,
           a.agent_role              AS agent_role,
           count(*)                  AS attempts,
           count(*) FILTER (WHERE a.sqlstate = '40001') AS restarts,
           count(*) FILTER (WHERE a.sqlstate = '23514') AS refused_check,
           count(*) FILTER (WHERE a.sqlstate = '23503') AS refused_fk,
           count(*) FILTER (WHERE a.sqlstate = '23505') AS refused_unique,
           count(*) FILTER (WHERE a.sqlstate = 'P0001') AS refused_raise,
           -- Broken out because it is the S22 signature: a missing write policy under
           -- FORCE ROW LEVEL SECURITY refuses with exactly this code, on one role at a
           -- time, and it is the most diagnosable failure in the deployment.
           count(*) FILTER (WHERE a.sqlstate = '42501') AS insufficient_privilege,
           count(*) FILTER (WHERE a.sqlstate IS NOT NULL
                 AND a.sqlstate NOT IN
                 ('40001', '23514', '23503', '23505', 'P0001', '42501')) AS unmodelled,
           max(a.at)                 AS last_at
      FROM mainline_meas.agent_action a
     WHERE a.at > now() - INTERVAL '21 days'
     GROUP BY date_trunc('day', a.at), a.agent_role
  ),
  t AS (SELECT count(*) AS group_count FROM g)
  SELECT g.d                      AS d,
         g.agent_role             AS agent_role,
         g.attempts               AS attempts,
         g.restarts               AS restarts,
         g.refused_check          AS refused_check,
         g.refused_fk             AS refused_fk,
         g.refused_unique         AS refused_unique,
         g.refused_raise          AS refused_raise,
         g.insufficient_privilege AS insufficient_privilege,
         g.unmodelled             AS unmodelled,
         g.last_at                AS last_at,
         -- Fail-closed completeness for this channel: every failure in the group is one
         -- the invariant catalogue models and the retry policy knows what to do with.
         (g.unmodelled = 0)       AS outcomes_modelled,
         t.group_count            AS group_count,
         (t.group_count <= 25)    AS rows_complete
    FROM g CROSS JOIN t
   ORDER BY g.d DESC, g.restarts DESC, g.agent_role
   LIMIT 25;
