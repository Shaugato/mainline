-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- MAINLINE · 0181d_policy_permit_service_read.sql
-- CREATE POLICY service_read ON mainline.permit — the half of S22 §11.3 does not spell out
--
-- MI: MI02, MI22
-- I: I02
-- COUNSEL-GATED: no
-- RATIONALE: An UPDATE with a WHERE clause evaluates the SELECT policies as well as the
--            UPDATE policy. A trigger running as `svc_disposition` that cannot SEE the
--            permit row cannot decrement its counter, and the gate transaction dies with
--            42501 instead of with a refusal anyone can read. This policy is why the write
--            policies work.
--
-- migration:  0181d_policy_permit_service_read
-- domain:     datamodel / dm-views-rls
-- band:       0180-0198z · datamodel/dm-views-rls · AUTHORED, allocated by
--             verticals/mainline/db/migrations.allocation.toml (MR-6 lock 1)
-- statements: 1
-- matrix:     verticals/mainline/db/RLS-MATRIX.yaml — this file is a RENDERING of one entry
--             there; tests/integration/schema/test_mi_rls.py asserts the two agree
-- source:     ARCHITECTURE.md §11.3 (RLS, SEC-1) · §4.1 law 10 · correction S22 · §5.11 (the trigger graph) · verticals/mainline/db/GRANTS.yaml (open coupling)
-- requires:   0050 mainline.permit · 0181 ENABLE · 0181a FORCE
-- sqlstate:   42501 — this is the policy whose absence produces it, on a read nobody wrote by hand.
-- forward-only; no .down.sql exists at or below the protected floor.
--
-- ────────────────────────────────────────────────────────────────────────────
-- THE ROLE LIST IS THE TRIGGER GRAPH, NOT A CONVENIENCE
-- ────────────────────────────────────────────────────────────────────────────
-- `agent_gate` (fn_check_materialised, proc_merge_permit), `svc_disposition`
-- (fn_disposition_close, fn_disposition_retract_only), `agent_recaller` and
-- `agent_projector` (which read the subject they are computing about), `agent_cartographer`
-- and `agent_ingestor` (schema-wide SELECT on `mainline`, and outbox triggers that fire on
-- tables they write), `agent_patroller` and `agent_fleet` (drift and propagation both
-- resolve to a subject). Every one of them holds SELECT on schema `mainline` in GRANTS.yaml
-- already; without this policy the grant is live and the rows are invisible, which is the
-- most confusing failure mode RLS has.
--
-- ────────────────────────────────────────────────────────────────────────────
-- WHY NOT ONE POLICY `TO PUBLIC USING (true)`
-- ────────────────────────────────────────────────────────────────────────────
-- Because then `site_reader` would match it too, and `site_scope` would become decorative:
-- permissive policies OR together, so a single PUBLIC policy returning true makes every
-- narrower permissive policy on the same command unreachable. The role list is the
-- mechanism.
--

CREATE POLICY service_read ON mainline.permit
  AS PERMISSIVE FOR SELECT
  TO agent_gate, svc_disposition, agent_recaller, agent_projector,
     agent_cartographer, agent_ingestor, agent_patroller, agent_fleet
  USING (true);

