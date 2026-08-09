-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- MAINLINE · 0181h_policy_permit_hold_blocks_delete.sql
-- CREATE POLICY hold_blocks_delete ON mainline.permit — RESTRICTIVE, and deliberately redundant
--
-- MI: MI01
-- I: I01
-- COUNSEL-GATED: no
-- RATIONALE: The Crimes (Document Destruction) Act 2006 (Vic) makes it an offence
--            punishable by five years' imprisonment to destroy a document knowing it is
--            reasonably likely to be required in evidence. A permit under legal hold is
--            exactly such a document. That is worth three independent layers, and this is
--            layer three.
--
-- migration:  0181h_policy_permit_hold_blocks_delete
-- domain:     datamodel / dm-views-rls
-- band:       0180-0198z · datamodel/dm-views-rls · AUTHORED, allocated by
--             verticals/mainline/db/migrations.allocation.toml (MR-6 lock 1)
-- statements: 1
-- matrix:     verticals/mainline/db/RLS-MATRIX.yaml — this file is a RENDERING of one entry
--             there; tests/integration/schema/test_mi_rls.py asserts the two agree
-- source:     ARCHITECTURE.md §11.3 (RLS, SEC-1) · §4.1 law 10 · correction S22 · §11.6 · verticals/mainline/db/GRANTS.yaml denials (no role holds DELETE)
-- requires:   0050 mainline.permit · 0181 ENABLE · 0181a FORCE
-- sqlstate:   42501 on a DELETE of a held permit, from any role including one that somehow holds DELETE.
-- forward-only; no .down.sql exists at or below the protected floor.
--
-- ────────────────────────────────────────────────────────────────────────────
-- RESTRICTIVE MEANS AND, NOT OR
-- ────────────────────────────────────────────────────────────────────────────
-- Permissive policies OR together and widen the visible set; restrictive policies AND with
-- the result and narrow it. A permissive `USING (under_hold = false)` would be useless here
-- — any other permissive DELETE policy would OR straight past it. RESTRICTIVE `TO PUBLIC`
-- means every role, including one added tomorrow by someone who never read this file.
--
-- ────────────────────────────────────────────────────────────────────────────
-- WHY A REDUNDANT LAYER IS NOT A WASTED ONE
-- ────────────────────────────────────────────────────────────────────────────
-- Layer one is the grant: GRANTS.yaml's last denial is that NO ROLE IN THE MATRIX HOLDS
-- DELETE ON ANYTHING. Layer two is the append-only trigger family (0128*), which raises
-- P0001. This is layer three, and it is the only one of the three that survives a `GRANT
-- DELETE` typed by an admin at 3 a.m. Permitted deletion is a reviewed two-person job that
-- writes a `destruction_record`; it is not a privilege any standing role carries and it is
-- not something this policy is meant to be argued around.
--

CREATE POLICY hold_blocks_delete ON mainline.permit
  AS RESTRICTIVE FOR DELETE TO PUBLIC
  USING (under_hold = false);

