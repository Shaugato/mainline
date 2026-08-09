-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- MAINLINE · 0187d_policy_standing_assay_insert.sql
-- CREATE POLICY standing_assay_insert ON mainline_meas.standing
--
-- MI: MI28
-- I: I15
-- COUNSEL-GATED: yes
-- RATIONALE: S22's INSERT arm. M10 ships inert, and inert is not the same as unwritten: an
--            inert mechanism that still records W = 1.0 for every hazard class leaves a
--            dated, queryable record of the fact that it was inert, which is what makes its
--            later activation discoverable rather than a deployment.
--
-- migration:  0187d_policy_standing_assay_insert
-- domain:     datamodel / dm-views-rls
-- band:       0180-0198z · datamodel/dm-views-rls · AUTHORED, allocated by
--             verticals/mainline/db/migrations.allocation.toml (MR-6 lock 1)
-- statements: 1
-- matrix:     verticals/mainline/db/RLS-MATRIX.yaml — this file is a RENDERING of one entry
--             there; tests/integration/schema/test_mi_rls.py asserts the two agree
-- source:     ARCHITECTURE.md §11.3 (RLS, SEC-1) · §4.1 law 10 · correction S22 · §11.5 · §11.2
-- requires:   0089 mainline_meas.standing · 0187 ENABLE · 0187a FORCE
-- sqlstate:   42501 when absent — and a silently uncomputed measure, which is worse.
-- forward-only; no .down.sql exists at or below the protected floor.
--
-- ────────────────────────────────────────────────────────────────────────────
-- THE CONSTRAINT THAT ACTUALLY GATES THIS INSERT IS NOT IN THIS FILE
-- ────────────────────────────────────────────────────────────────────────────
-- `standing.within_policy CHECK (window_from >= policy_effective_from)` plus the NOT NULL
-- FK to `person_measure_policy` is what makes SEC-3 a row the database requires: a standing
-- score computed over data predating the signed, notified customer policy is not an
-- insertable row, and the refusal is 23514. `WITH CHECK (true)` here is deliberate — the
-- policy layer must not appear to duplicate a control it cannot express, because a policy
-- expression may not contain a subquery and could never reach the policy table.
--

CREATE POLICY standing_assay_insert ON mainline_meas.standing
  AS PERMISSIVE FOR INSERT TO agent_assay
  WITH CHECK (true);

