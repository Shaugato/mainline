-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- MAINLINE · 0183e_policy_cr_view_owner_read.sql
-- CREATE POLICY cr_view_owner_read ON mainline.change_request
--
-- MI: MI30, MI22
-- I: I02
-- COUNSEL-GATED: no
-- RATIONALE: The audit views read both gated subjects and evaluate as their owner under
--            FORCE. Without this, a view that joins permits and change requests silently
--            returns only the permit half — a partial answer that carries no indication it
--            is partial, which is the exact failure mode the whole `rows_complete` contract
--            exists to prevent.
--
-- migration:  0183e_policy_cr_view_owner_read
-- domain:     datamodel / dm-views-rls
-- band:       0180-0198z · datamodel/dm-views-rls · AUTHORED, allocated by
--             verticals/mainline/db/migrations.allocation.toml (MR-6 lock 1)
-- statements: 1
-- matrix:     verticals/mainline/db/RLS-MATRIX.yaml — this file is a RENDERING of one entry
--             there; tests/integration/schema/test_mi_rls.py asserts the two agree
-- source:     ARCHITECTURE.md §11.3 (RLS, SEC-1) · §4.1 law 10 · correction S22 · v26.2 row-level-security reference · §17
-- requires:   0051 mainline.change_request · 0183 ENABLE · 0183a FORCE
-- sqlstate:   none visible — the failure is an empty or partial result, not an error.
-- forward-only; no .down.sql exists at or below the protected floor.
--
-- Both `mainline_owner` and `mainline_migrator`, for the reason set out in 0181e: a newly
-- created object is owned by the role that created it, and this file cannot know which role
-- the runner connected as.
--

CREATE POLICY cr_view_owner_read ON mainline.change_request
  AS PERMISSIVE FOR SELECT TO mainline_owner, mainline_migrator
  USING (true);

