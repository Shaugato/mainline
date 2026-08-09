-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- MAINLINE · 0187c_policy_standing_assay_read.sql
-- CREATE POLICY standing_assay_read ON mainline_meas.standing
--
-- MI: MI28
-- I: I15
-- COUNSEL-GATED: yes
-- RATIONALE: The role that computes the measure reads back the window it is extending — a
--            standing score is computed over a window that begins where the last one ended,
--            so the computation is not expressible without the prior row. `agent_assay` is
--            confined to `mainline_meas` and holds no reach into `mainline` at all.
--
-- migration:  0187c_policy_standing_assay_read
-- domain:     datamodel / dm-views-rls
-- band:       0180-0198z · datamodel/dm-views-rls · AUTHORED, allocated by
--             verticals/mainline/db/migrations.allocation.toml (MR-6 lock 1)
-- statements: 1
-- matrix:     verticals/mainline/db/RLS-MATRIX.yaml — this file is a RENDERING of one entry
--             there; tests/integration/schema/test_mi_rls.py asserts the two agree
-- source:     ARCHITECTURE.md §11.3 (RLS, SEC-1) · §4.1 law 10 · correction S22 · §11.2 (agent_assay) · §5.7
-- requires:   0089 mainline_meas.standing · 0187 ENABLE · 0187a FORCE
-- sqlstate:   42501 when absent.
-- forward-only; no .down.sql exists at or below the protected floor.
--
-- `agent_assay` is not narrowed by `standing_blind`, which names `signer`. The two roles
-- are disjoint by construction and no human is ever granted a service role — every role in
-- GRANTS.yaml is NOLOGIN, reached by GRANT plus SET ROLE, precisely so that CURRENT_USER is
-- a scope token rather than a login choice.
--

CREATE POLICY standing_assay_read ON mainline_meas.standing
  AS PERMISSIVE FOR SELECT TO agent_assay
  USING (true);

