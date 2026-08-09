-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- MAINLINE · 0183d_policy_cr_service_read.sql
-- CREATE POLICY cr_service_read ON mainline.change_request
--
-- MI: MI30, MI22
-- I: I02
-- COUNSEL-GATED: no
-- RATIONALE: The same trigger graph touches both subjects, so the same service roles need
--            to see the row they are about to update. Without this policy the change-
--            request arm of `fn_disposition_close` fails with 42501 while the permit arm
--            succeeds, which is the hardest class of bug to diagnose: half a trigger
--            working.
--
-- migration:  0183d_policy_cr_service_read
-- domain:     datamodel / dm-views-rls
-- band:       0180-0198z · datamodel/dm-views-rls · AUTHORED, allocated by
--             verticals/mainline/db/migrations.allocation.toml (MR-6 lock 1)
-- statements: 1
-- matrix:     verticals/mainline/db/RLS-MATRIX.yaml — this file is a RENDERING of one entry
--             there; tests/integration/schema/test_mi_rls.py asserts the two agree
-- source:     ARCHITECTURE.md §11.3 (RLS, SEC-1) · §4.1 law 10 · correction S22 · §5.11
-- requires:   0051 mainline.change_request · 0183 ENABLE · 0183a FORCE
-- sqlstate:   42501 — on one branch of one trigger, which is what makes it hard to find.
-- forward-only; no .down.sql exists at or below the protected floor.
--
-- The role list is identical to 0181d's by construction rather than by copying: it is the
-- set of roles whose triggers or queries resolve a gated subject, and GSAC (DM-2) made that
-- set the same for both subjects on purpose.
--

CREATE POLICY cr_service_read ON mainline.change_request
  AS PERMISSIVE FOR SELECT
  TO agent_gate, svc_disposition, agent_recaller, agent_projector,
     agent_cartographer, agent_ingestor, agent_patroller, agent_fleet
  USING (true);

