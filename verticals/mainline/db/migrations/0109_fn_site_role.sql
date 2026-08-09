-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- MAINLINE · 0109_fn_site_role.sql
-- CREATE FUNCTION mainline.fn_site_role — the tenancy token is projected, never supplied
--
-- MI: MI01
-- I: I01
-- COUNSEL-GATED: no
-- RATIONALE: Row-level security policy expressions cannot contain subqueries on this
--            platform, so tenancy scope is a denormalised role-name token compared against
--            CURRENT_USER. If the writer supplies that token the writer chooses which
--            tenant can see the row, and row-level security becomes an application-
--            cooperative control — worthless against exactly the adversary it constrains.
--            This projects the token from the site row and refuses when there is none. It
--            ships without a weld because the only trigger on a gated subject table is the
--            merge gate, and that ruling is not this worker to relax.
--
-- @rendered-by  trappoint render
-- @template     packages/trappoint-sql/templates/0108_fn_site_role.sql.j2
-- @binding      verticals/mainline/vertical.toml
-- DO NOT EDIT. `trappoint render --check` is a zero-diff assertion in CI, so a
-- hand edit here is a red build, not a silent divergence.
--
-- migration:  0109_fn_site_role
-- band:       0100-0109z · kernel/projection-triggers · RENDERED
-- statements: 1
-- invariants: MI01 in its access-control aspect: an evidentiary row whose scope token was chosen
--             by its writer is a row whose visibility the writer controls.
-- source:     ARCHITECTURE.md §5.11 (listed trigger family) · §4.1 law 10 · §11.3 ·
--             verticals/mainline/db/migrations/0020a_site.sql (the authoritative source for
--             every projected site_role, site_code and tenant_id in the schema)
-- requires:   mainline.site (site_id, site_role)
-- provides:   mainline.fn_site_role() — DELIBERATELY UNWELDED IN THIS BAND. See the
--             header comment: the relations carrying site_role are the gated subjects, and the
--             kernel's acyclicity ruling reserves their trigger slot for the merge gate.
-- sqlstate:   P0001 when the site row is absent. Never a default, never a session variable,
--             never the value the inserter supplied.
-- forward-only; no .down.sql and no .up.sql (MR-5).
--
-- ACYCLICITY. Unwelded. If a later migration welds it BEFORE INSERT on a relation, it reads one
-- row of `site` and writes only NEW, contributing depth 0.

CREATE FUNCTION mainline.fn_site_role() RETURNS TRIGGER LANGUAGE PLpgSQL AS $$
DECLARE
  v_site_role NAME;
BEGIN
  SELECT st.site_role INTO v_site_role
    FROM mainline.site st
   WHERE st.site_id = (NEW).site_id;

  IF v_site_role IS NULL THEN
    RAISE EXCEPTION USING ERRCODE='P0001',
      MESSAGE='MAINLINE: no site row for this record — the tenancy scope token has no source';
  END IF;

  -- UNCONDITIONAL, exactly as every other projection here: a supplied token is overwritten
  -- whether or not it agrees, so a correct guess confers no privilege.
  NEW.site_role := v_site_role;
  RETURN NEW;
END $$;
