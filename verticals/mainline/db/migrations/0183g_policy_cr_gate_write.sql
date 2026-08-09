-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- MAINLINE · 0183g_policy_cr_gate_write.sql
-- CREATE POLICY cr_gate_write ON mainline.change_request — both writer roles
--
-- MI: MI30, MI22
-- I: I02
-- COUNSEL-GATED: no
-- RATIONALE: CF-31 merges a change request carrying an undispositioned `weaken_over_blood`
--            check and expects 23514 on `cr_gate_closed_when_merged`. That test can only
--            reach the CHECK if the counter was maintained, and the counter is maintained
--            by two triggers running as two different roles. Omit either and CF-31 fails
--            with 42501 — the right answer for the wrong reason, which is the worst kind of
--            green test.
--
-- migration:  0183g_policy_cr_gate_write
-- domain:     datamodel / dm-views-rls
-- band:       0180-0198z · datamodel/dm-views-rls · AUTHORED, allocated by
--             verticals/mainline/db/migrations.allocation.toml (MR-6 lock 1)
-- statements: 1
-- matrix:     verticals/mainline/db/RLS-MATRIX.yaml — this file is a RENDERING of one entry
--             there; tests/integration/schema/test_mi_rls.py asserts the two agree
-- source:     ARCHITECTURE.md §11.3 (RLS, SEC-1) · §4.1 law 10 · correction S22 · conformance cases CF-22, CF-31
-- requires:   0051 mainline.change_request · 0183 ENABLE · 0183a FORCE · 0121 trg_check_materialised · 0123 trg_disposition_close
-- sqlstate:   NONE when absent — the UPDATE matches zero rows and returns successfully; see the
--             measured block in 0181g. 23514 on cr_gate_closed_when_merged when present and
--             working, which is the outcome CF-31 is actually asserting.
-- forward-only; no .down.sql exists at or below the protected floor.
--
-- `agent_gate` and `svc_disposition`, exactly as on the permit, and for exactly the same
-- reason: no trigger function in 0100-0149 is SECURITY DEFINER, so each trigger writes as
-- whoever invoked it. If that ever changes, both files change together.
--

CREATE POLICY cr_gate_write ON mainline.change_request
  AS PERMISSIVE FOR UPDATE TO agent_gate, svc_disposition
  USING (true) WITH CHECK (true);

