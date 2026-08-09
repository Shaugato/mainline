-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- MAINLINE · 0164_v_agent_actions.sql
-- CREATE VIEW mainline_audit.v_agent_actions — what the fleet did, by role, tool and outcome
--
-- MI: MI01, MI22
-- I: I15
-- COUNSEL-GATED: no
-- RATIONALE: `outcome = 'refused'` is the product working. This is the only view in the band
--            where a rising number is good news, and reporting it beside 'ok' and 'error' is
--            what stops a refusal being read as an incident. It is also the surface on which
--            the separation covenant becomes checkable in operation rather than in the grant
--            matrix: if `agent_recaller` ever appears with a tool that writes an obligation,
--            the covenant broke and this is where it shows.
--
-- migration:  0164_v_agent_actions
-- domain:     datamodel / dm-views-rls
-- band:       0155-0169z · datamodel/dm-views-rls · AUTHORED (migrations.allocation.toml, MR-6 lock 1)
-- statements: 1
-- invariants: MI01 — evidentiary tables are append-only; `agent_action` is one of them and
--                    this view never mutates it.
--             MI22 — a stale projection fails closed; `last_at` is how staleness is read.
--             I15  — THE ALLEGATION FIREWALL, and it is the reason this view groups on
--                    `agent_role` and never on `signer_sub`. See below.
-- source:     ARCHITECTURE.md §17 (view definition) · §5.7 (agent_action DDL) · §11.5
--             (SEC-3, the A-RULE) · §12 (Class A vs Class B telemetry) · §9.1
-- requires:   0089 mainline_meas.agent_action
-- sqlstate:   none — this object refuses nothing.
-- forward-only; no .down.sql exists at or below the protected floor.
--
-- ─────────────────────────────────────────────────────────────────────────────
-- I15 / SEC-3: WHY THIS VIEW GROUPS ON A ROLE AND NEVER ON A PERSON
-- ─────────────────────────────────────────────────────────────────────────────
-- `agent_action.agent_role` maps 1:1 to the SQL role that executed the action.
-- It is a MACHINE. Grouping on it produces a distribution about software.
--
-- The table also carries `subject_id`, and a permit has an actor. Joining that
-- through to a person and grouping on it would produce a per-named-human
-- distribution — and §11.5 is unambiguous that `signer_sub` is a SPAN ATTRIBUTE,
-- NEVER A METRIC LABEL: "a dimension we cannot aggregate on is a dimension we
-- cannot accidentally publish." Per-signer detail exists in exactly one place,
-- `mainline_qa`, where every SELECT writes a `profile_read` ledger entry and no
-- MCP service account is ever issued, on any tier, ever (S14).
--
-- So this view is bounded by construction rather than by intention: it selects
-- three grouping columns, all of which describe software, and there is no join
-- in it that could reach a name.
--
-- ─────────────────────────────────────────────────────────────────────────────
-- WHY `refused` IS COUNTED SEPARATELY AND WHY THE SQLSTATE IS CARRIED
-- ─────────────────────────────────────────────────────────────────────────────
-- §16: `40001` is the only retryable code; `23514`, `23503`, `23505` and `P0001`
-- are GATE REFUSALS — attempted exactly once, ever, and written to the refusal
-- ledger with the constraint name. Any other SQLSTATE means the database refused
-- for a reason nobody modelled, and `unmodelled_refusals` is that count.
--
-- A non-zero `unmodelled_refusals` is the most actionable number on this entire
-- surface, and it is invisible in any grouping that lumps all failures together.
--
-- ─────────────────────────────────────────────────────────────────────────────
-- WHAT THIS VIEW IS NOT
-- ─────────────────────────────────────────────────────────────────────────────
-- IT IS NOT EVIDENCE THAT A CONDITION EXISTS. §9.4: an LLM ops report is
-- evidence that a review occurred, not evidence of a condition. The same applies
-- one level down — this view is evidence that an action was attempted with a
-- given outcome, and the outcome's meaning lives in the row's `input_sha256` /
-- `output_sha256` pair, which is deliberately not on this surface because two
-- 32-byte digests per row would blow the 10 KiB cap at ~40 rows.

CREATE VIEW mainline_audit.v_agent_actions AS
  WITH g AS (
    SELECT a.agent_role                        AS agent_role,
           a.tool                              AS tool,
           a.outcome                           AS outcome,
           count(*)                            AS n,
           max(a.at)                           AS last_at,
           count(DISTINCT a.transport)         AS transports,
           count(*) FILTER (WHERE a.sqlstate = '40001')          AS retryable,
           count(*) FILTER (WHERE a.sqlstate IN
                 ('23514', '23503', '23505', 'P0001'))           AS modelled_refusals,
           count(*) FILTER (WHERE a.sqlstate IS NOT NULL
                 AND a.sqlstate NOT IN
                 ('40001', '23514', '23503', '23505', 'P0001'))  AS unmodelled_refusals,
           count(DISTINCT a.model_id)          AS model_ids,
           count(DISTINCT a.prompt_version)    AS prompt_versions,
           round(avg(a.latency_ms)::NUMERIC, 1) AS mean_latency_ms
      FROM mainline_meas.agent_action a
     WHERE a.at > now() - INTERVAL '7 days'
     GROUP BY a.agent_role, a.tool, a.outcome
  ),
  t AS (SELECT count(*) AS group_count FROM g)
  SELECT g.agent_role          AS agent_role,
         g.tool                AS tool,
         g.outcome             AS outcome,
         g.n                   AS n,
         g.last_at             AS last_at,
         g.transports          AS transports,
         g.retryable           AS retryable,
         g.modelled_refusals   AS modelled_refusals,
         g.unmodelled_refusals AS unmodelled_refusals,
         g.model_ids           AS model_ids,
         g.prompt_versions     AS prompt_versions,
         g.mean_latency_ms     AS mean_latency_ms,
         -- The completeness flag in this channel's terms: every failure in this group was
         -- one the invariant catalogue models. Fail-closed — an unmodelled SQLSTATE is a
         -- refusal nobody designed, so the group reports false.
         (g.unmodelled_refusals = 0) AS outcomes_modelled,
         t.group_count         AS group_count,
         (t.group_count <= 25) AS rows_complete
    FROM g CROSS JOIN t
   ORDER BY g.n DESC, g.agent_role, g.tool, g.outcome
   LIMIT 25;
