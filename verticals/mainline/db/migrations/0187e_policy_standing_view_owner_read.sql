-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- MAINLINE · 0187e_policy_standing_view_owner_read.sql
-- CREATE POLICY standing_view_owner_read ON mainline_meas.standing
--
-- MI: MI28
-- I: I15
-- COUNSEL-GATED: yes
-- RATIONALE: `mainline_qa.v_standing_components` and `mainline_qa.v_my_record` read this
--            table and evaluate as their owner under FORCE. Without this policy SEC-3
--            condition (4) fails silently — the person asks for their record and receives
--            an empty result, which is operationally identical to a refusal and legally
--            worse, because it is undated and unattributed.
--
-- migration:  0187e_policy_standing_view_owner_read
-- domain:     datamodel / dm-views-rls
-- band:       0180-0198z · datamodel/dm-views-rls · AUTHORED, allocated by
--             verticals/mainline/db/migrations.allocation.toml (MR-6 lock 1)
-- statements: 1
-- matrix:     verticals/mainline/db/RLS-MATRIX.yaml — this file is a RENDERING of one entry
--             there; tests/integration/schema/test_mi_rls.py asserts the two agree
-- source:     ARCHITECTURE.md §11.3 (RLS, SEC-1) · §4.1 law 10 · correction S22 · §11.5 (SEC-3 condition 4) · v26.2 row-level-security reference
-- requires:   0089 mainline_meas.standing · 0187 ENABLE · 0187a FORCE
-- sqlstate:   none visible — an empty disclosure, which is the failure this file prevents.
-- forward-only; no .down.sql exists at or below the protected floor.
--
-- ────────────────────────────────────────────────────────────────────────────
-- WHAT THIS POLICY DOES NOT GRANT, SAID EXPLICITLY BECAUSE IT LOOKS LIKE IT MIGHT
-- ────────────────────────────────────────────────────────────────────────────
-- It gives the VIEW OWNER an unfiltered read of the base table. It gives no `mainline_qa`
-- privilege to any MCP identity, because there is none to give: S14 is that no MCP service
-- account is ever issued for `mainline_qa`, on any tier, ever, and the nightly surface test
-- asserts the schema is UNREACHABLE from `mainline_auditor` as a negative assertion beside
-- the positive ones. A Managed-MCP account for per-named-person distributions is the single
-- worst credential this system could issue.
--
-- ────────────────────────────────────────────────────────────────────────────
-- AND WHY THE VIEW STILL ONLY SHOWS THE SUBJECT THEIR OWN ROW
-- ────────────────────────────────────────────────────────────────────────────
-- `v_my_record` carries `WHERE st.actor_sub = current_user` in its body. The owner policy
-- removes the RLS filter on the base table; the view's own predicate is what scopes the
-- result. Two different mechanisms doing two different jobs, and 0172's header explains why
-- a view cannot use the first for the second.
--

CREATE POLICY standing_view_owner_read ON mainline_meas.standing
  AS PERMISSIVE FOR SELECT TO mainline_owner, mainline_migrator
  USING (true);

