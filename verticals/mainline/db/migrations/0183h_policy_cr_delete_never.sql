-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- MAINLINE · 0183h_policy_cr_delete_never.sql
-- CREATE POLICY cr_delete_never ON mainline.change_request — RESTRICTIVE, unconditional
--
-- MI: MI01
-- I: I01
-- COUNSEL-GATED: no
-- RATIONALE: The permit's `hold_blocks_delete` reads `under_hold`. `change_request` has no
--            such column, and inventing one here to make the mirror pretty would be adding
--            a legal-hold flag nothing maintains — a control that looks like the permit's
--            and is a decoration. The honest mirror is unconditional: MI01, and no role in
--            the matrix holds DELETE.
--
-- migration:  0183h_policy_cr_delete_never
-- domain:     datamodel / dm-views-rls
-- band:       0180-0198z · datamodel/dm-views-rls · AUTHORED, allocated by
--             verticals/mainline/db/migrations.allocation.toml (MR-6 lock 1)
-- statements: 1
-- matrix:     verticals/mainline/db/RLS-MATRIX.yaml — this file is a RENDERING of one entry
--             there; tests/integration/schema/test_mi_rls.py asserts the two agree
-- source:     ARCHITECTURE.md §11.3 (RLS, SEC-1) · §4.1 law 10 · correction S22 · §16 MI01 · verticals/mainline/db/GRANTS.yaml denials
-- requires:   0051 mainline.change_request · 0183 ENABLE · 0183a FORCE
-- sqlstate:   42501 on any DELETE, from any role.
-- forward-only; no .down.sql exists at or below the protected floor.
--
-- ────────────────────────────────────────────────────────────────────────────
-- WHY UNCONDITIONAL IS STRONGER HERE, NOT WEAKER
-- ────────────────────────────────────────────────────────────────────────────
-- `USING (false)` is I01's RESTRICTIVE-RLS leg in its purest form: no row of this table is
-- deletable by anyone, ever, under any condition. The permit's policy is the weaker of the
-- two precisely because it is conditional — an unheld permit is deletable by a role that
-- holds DELETE, and the reason that is acceptable there is that no such role exists and a
-- held permit is the one with legal exposure. Here there is no hold flag to condition on,
-- so the strict form is also the only expressible one, and it happens to be the better one.
--

CREATE POLICY cr_delete_never ON mainline.change_request
  AS RESTRICTIVE FOR DELETE TO PUBLIC
  USING (false);

