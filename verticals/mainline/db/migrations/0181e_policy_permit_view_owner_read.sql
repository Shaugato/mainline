-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- MAINLINE · 0181e_policy_permit_view_owner_read.sql
-- CREATE POLICY view_owner_read ON mainline.permit — so the audit surface is not empty
--
-- MI: MI02, MI22
-- I: I02
-- COUNSEL-GATED: no
-- RATIONALE: A view evaluates RLS as its owner and FORCE means the owner is not exempt, so
--            every `mainline_audit` view over this table returns zero rows without this
--            policy. Zero rows on an audit surface is the worst failure available: it reads
--            exactly like a site with nothing wrong, and the reader has no way to tell the
--            difference.
--
-- migration:  0181e_policy_permit_view_owner_read
-- domain:     datamodel / dm-views-rls
-- band:       0180-0198z · datamodel/dm-views-rls · AUTHORED, allocated by
--             verticals/mainline/db/migrations.allocation.toml (MR-6 lock 1)
-- statements: 1
-- matrix:     verticals/mainline/db/RLS-MATRIX.yaml — this file is a RENDERING of one entry
--             there; tests/integration/schema/test_mi_rls.py asserts the two agree
-- source:     ARCHITECTURE.md §11.3 (RLS, SEC-1) · §4.1 law 10 · correction S22 · v26.2 row-level-security reference (view owner evaluation, security_invoker) · §17
-- requires:   0050 mainline.permit · 0181 ENABLE · 0181a FORCE
-- sqlstate:   42501 on the view, or — worse and more likely — an empty result with no error at all.
-- forward-only; no .down.sql exists at or below the protected floor.
--
-- ────────────────────────────────────────────────────────────────────────────
-- TWO ROLES, BECAUSE THE OWNER IS WHOEVER RAN CREATE VIEW
-- ────────────────────────────────────────────────────────────────────────────
-- A newly created object is owned by the role that created it. Migrations 0002-0006
-- transfer SCHEMA ownership to `mainline_owner`, which does not retroactively own objects a
-- later migration creates; those are owned by the role the runner connected as, which is
-- `mainline_migrator` in the designed deployment and may be an admin in a test cluster.
-- Naming both is not hedging — it is the honest consequence of the fact that this file
-- cannot know which role applied it.
--
-- ────────────────────────────────────────────────────────────────────────────
-- WHY NOT JUST DROP FORCE
-- ────────────────────────────────────────────────────────────────────────────
-- Dropping FORCE would give `mainline_owner` the same reach with no object to point at.
-- This way the owner's read is ONE NAMED, DIFFABLE, REVOCABLE POLICY that a reviewer can
-- see in `SHOW POLICIES` and a test can assert. An exemption is invisible; a policy is an
-- exhibit. DM-10's argument about constraint names is the same argument.
--

CREATE POLICY view_owner_read ON mainline.permit
  AS PERMISSIVE FOR SELECT TO mainline_owner, mainline_migrator
  USING (true);

