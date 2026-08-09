-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- MAINLINE · 0183c_policy_cr_fleet_scope.sql
-- CREATE POLICY cr_fleet_scope ON mainline.change_request
--
-- MI: MI30
-- I: I02
-- COUNSEL-GATED: no
-- RATIONALE: The same three cross-site readers as the permit's `fleet_scope`. The MOC
--            Ancestry Audit is a fleet-level exercise over change requests specifically, so
--            an auditor scoped to one site could not run the audit the product is
--            demonstrated with.
--
-- migration:  0183c_policy_cr_fleet_scope
-- domain:     datamodel / dm-views-rls
-- band:       0180-0198z · datamodel/dm-views-rls · AUTHORED, allocated by
--             verticals/mainline/db/migrations.allocation.toml (MR-6 lock 1)
-- statements: 1
-- matrix:     verticals/mainline/db/RLS-MATRIX.yaml — this file is a RENDERING of one entry
--             there; tests/integration/schema/test_mi_rls.py asserts the two agree
-- source:     ARCHITECTURE.md §11.3 (RLS, SEC-1) · §4.1 law 10 · correction S22 · §11.2 · §9.1
-- requires:   0051 mainline.change_request · 0183 ENABLE · 0183a FORCE
-- sqlstate:   42501 for any role with no other SELECT policy here.
-- forward-only; no .down.sql exists at or below the protected floor.
--
-- `mainline_auditor` is listed for the reason given in full in 0181c: the grant is the
-- binding control and a policy cannot widen a privilege that was never granted; the listing
-- exists so the audit views' owner-evaluated reads work by design rather than by accident.
--

CREATE POLICY cr_fleet_scope ON mainline.change_request
  AS PERMISSIVE FOR SELECT TO fleet_hse, auditor_ro, mainline_auditor
  USING (true);

