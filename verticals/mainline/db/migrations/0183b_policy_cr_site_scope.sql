-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- MAINLINE · 0183b_policy_cr_site_scope.sql
-- CREATE POLICY cr_site_scope ON mainline.change_request
--
-- MI: MI30
-- I: I02
-- COUNSEL-GATED: no
-- RATIONALE: `change_request.site_role` is the same NAME token as the permit's, projected
--            from the same authoritative `mainline.site` row, so the scope shape is
--            identical and so is its argument: no subqueries in a policy expression,
--            therefore a denormalised role name, therefore a column an inserter cannot
--            choose.
--
-- migration:  0183b_policy_cr_site_scope
-- domain:     datamodel / dm-views-rls
-- band:       0180-0198z · datamodel/dm-views-rls · AUTHORED, allocated by
--             verticals/mainline/db/migrations.allocation.toml (MR-6 lock 1)
-- statements: 1
-- matrix:     verticals/mainline/db/RLS-MATRIX.yaml — this file is a RENDERING of one entry
--             there; tests/integration/schema/test_mi_rls.py asserts the two agree
-- source:     ARCHITECTURE.md §11.3 (RLS, SEC-1) · §4.1 law 10 · correction S22 · §4.1 law 10 · docs/leads/datamodel.md DM-3
-- requires:   0051 mainline.change_request · 0183 ENABLE · 0183a FORCE · 0020a mainline.site
-- sqlstate:   42501 for a site_reader outside its own site.
-- forward-only; no .down.sql exists at or below the protected floor.
--
-- The policy NAME is prefixed `cr_` while the permit's is not. That asymmetry is deliberate
-- and it is not cosmetic: policy names are scoped per table, so both could legally be
-- `site_scope`, and a test asserting 'site_scope exists' would then pass against a cluster
-- carrying only one of them. DM-10's rule is that the name is the exhibit; two exhibits
-- should not share a caption.
--

CREATE POLICY cr_site_scope ON mainline.change_request
  AS PERMISSIVE FOR SELECT TO site_reader
  USING (site_role = CURRENT_USER);

