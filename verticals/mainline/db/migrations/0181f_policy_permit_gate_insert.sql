-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- MAINLINE · 0181f_policy_permit_gate_insert.sql
-- CREATE POLICY gate_insert ON mainline.permit — S22, the INSERT arm
--
-- MI: MI02
-- I: I02
-- COUNSEL-GATED: no
-- RATIONALE: Under FORCE with no INSERT policy, `agent_gate` cannot open a permit at all.
--            The refusal is 42501 and it names no constraint, so it reads as a broken
--            deployment rather than as a designed refusal — which is precisely why S22 is a
--            correction and not a note.
--
-- migration:  0181f_policy_permit_gate_insert
-- domain:     datamodel / dm-views-rls
-- band:       0180-0198z · datamodel/dm-views-rls · AUTHORED, allocated by
--             verticals/mainline/db/migrations.allocation.toml (MR-6 lock 1)
-- statements: 1
-- matrix:     verticals/mainline/db/RLS-MATRIX.yaml — this file is a RENDERING of one entry
--             there; tests/integration/schema/test_mi_rls.py asserts the two agree
-- source:     ARCHITECTURE.md §11.3 (RLS, SEC-1) · §4.1 law 10 · correction S22 · conformance case CF-22
-- requires:   0050 mainline.permit · 0181 ENABLE · 0181a FORCE
-- sqlstate:   42501 when absent.
-- forward-only; no .down.sql exists at or below the protected floor.
--
-- ────────────────────────────────────────────────────────────────────────────
-- WITH CHECK AND NEVER USING
-- ────────────────────────────────────────────────────────────────────────────
-- An INSERT has no old row, so `USING` has nothing to evaluate against; PostgreSQL and
-- CockroachDB both take only `WITH CHECK` for a FOR INSERT policy. Writing `USING (true)`
-- here would be accepted as noise in some dialects and rejected in others, and either way
-- it would suggest the policy filters something it cannot see.
--
-- ────────────────────────────────────────────────────────────────────────────
-- WHY true, AND WHERE THE REAL CONSTRAINT LIVES
-- ────────────────────────────────────────────────────────────────────────────
-- The permit's site scope is enforced on READ. On WRITE the constraint that matters is not
-- row visibility but column authority: `site_role` is projected by `fn_site_role` from
-- `mainline.site`, and the seven CHECK constraints on the table refuse an issued permit
-- with open obligations. A policy expression cannot express any of that — no subqueries —
-- so pretending it does by writing something clever here would be a control that looks like
-- two and is one.
--

CREATE POLICY gate_insert ON mainline.permit
  AS PERMISSIVE FOR INSERT TO agent_gate
  WITH CHECK (true);

