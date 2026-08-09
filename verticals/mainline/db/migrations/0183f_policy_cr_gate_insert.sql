-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- MAINLINE · 0183f_policy_cr_gate_insert.sql
-- CREATE POLICY cr_gate_insert ON mainline.change_request
--
-- MI: MI30
-- I: I02
-- COUNSEL-GATED: no
-- RATIONALE: S22's INSERT arm, mirrored. Under FORCE with no INSERT policy the kernel
--            cannot open a change request, and the repository stops accepting commits with
--            a privilege error that names nothing.
--
-- migration:  0183f_policy_cr_gate_insert
-- domain:     datamodel / dm-views-rls
-- band:       0180-0198z · datamodel/dm-views-rls · AUTHORED, allocated by
--             verticals/mainline/db/migrations.allocation.toml (MR-6 lock 1)
-- statements: 1
-- matrix:     verticals/mainline/db/RLS-MATRIX.yaml — this file is a RENDERING of one entry
--             there; tests/integration/schema/test_mi_rls.py asserts the two agree
-- source:     ARCHITECTURE.md §11.3 (RLS, SEC-1) · §4.1 law 10 · correction S22
-- requires:   0051 mainline.change_request · 0183 ENABLE · 0183a FORCE
-- sqlstate:   42501 when absent.
-- forward-only; no .down.sql exists at or below the protected floor.
--
-- `WITH CHECK` and no `USING`, because an INSERT has no old row. See 0181f for the full
-- argument about why the expression is `true` and where the real write-time constraints
-- live — they are the four CHECKs on this table and the projections behind them, none of
-- which a policy expression could express.
--

CREATE POLICY cr_gate_insert ON mainline.change_request
  AS PERMISSIVE FOR INSERT TO agent_gate
  WITH CHECK (true);

