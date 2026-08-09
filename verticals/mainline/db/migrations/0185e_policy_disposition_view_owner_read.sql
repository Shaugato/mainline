-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- MAINLINE · 0185e_policy_disposition_view_owner_read.sql
-- CREATE POLICY disposition_view_owner_read ON mainline.disposition
--
-- MI: MI08
-- I: I15
-- COUNSEL-GATED: yes
-- RATIONALE: `v_weakenings_without_disposition`, `v_disposition_coverage` and the whole of
--            `mainline_qa` read this table and evaluate as their owner under FORCE. Without
--            this policy the audit surface reports every weakening as undispositioned,
--            because it cannot see the dispositions — an accusation surface that
--            manufactures its own accusations.
--
-- migration:  0185e_policy_disposition_view_owner_read
-- domain:     datamodel / dm-views-rls
-- band:       0180-0198z · datamodel/dm-views-rls · AUTHORED, allocated by
--             verticals/mainline/db/migrations.allocation.toml (MR-6 lock 1)
-- statements: 1
-- matrix:     verticals/mainline/db/RLS-MATRIX.yaml — this file is a RENDERING of one entry
--             there; tests/integration/schema/test_mi_rls.py asserts the two agree
-- source:     ARCHITECTURE.md §11.3 (RLS, SEC-1) · §4.1 law 10 · correction S22 · v26.2 row-level-security reference · §17
-- requires:   0066 mainline.disposition · 0180 peer_visible · 0185 ENABLE · 0185a FORCE
-- sqlstate:   none visible — the failure is a wrong answer, not an error, which is worse.
-- forward-only; no .down.sql exists at or below the protected floor.
--
-- ────────────────────────────────────────────────────────────────────────────
-- THE FAILURE THIS PREVENTS IS NOT AN EMPTY VIEW, IT IS A CONFIDENTLY WRONG ONE
-- ────────────────────────────────────────────────────────────────────────────
-- 0157's `NOT EXISTS (SELECT 1 FROM blocking_check JOIN disposition …)` is true whenever
-- the disposition is INVISIBLE, not only when it is absent. Under FORCE with no owner
-- policy, every disposition is invisible to the view, so every severity-4 weakening in the
-- corpus appears in an audit view titled 'weakenings without disposition'. That output is
-- not merely unhelpful; it is a self-generated exhibit asserting something false about our
-- own record, which is the one category of failure §11.1 ranks above a confidentiality
-- breach.
--
-- ────────────────────────────────────────────────────────────────────────────
-- AND WHY THAT IS AN ARGUMENT FOR FORCE, NOT AGAINST IT
-- ────────────────────────────────────────────────────────────────────────────
-- The alternative is not 'no risk' — it is the same read happening through an unnamed,
-- untestable owner exemption. Here the owner's read is one policy, in one file, that
-- `test_mi_rls.py` asserts by name and `test_mi_views.py` exercises by result.
--

CREATE POLICY disposition_view_owner_read ON mainline.disposition
  AS PERMISSIVE FOR SELECT TO mainline_owner, mainline_migrator
  USING (true);

