-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- MAINLINE · 0185h_policy_disposition_delete_never.sql
-- CREATE POLICY disposition_delete_never ON mainline.disposition — I01, on the table it matters most on
--
-- MI: MI01
-- I: I01
-- COUNSEL-GATED: yes
-- RATIONALE: A deleted disposition is a deleted signature over a deleted warning. There is
--            no legal hold flag to condition on and there should not be one: the answer is
--            unconditional. This is I01's RESTRICTIVE-RLS leg in its literal form — `USING
--            (false)`, every role, forever.
--
-- migration:  0185h_policy_disposition_delete_never
-- domain:     datamodel / dm-views-rls
-- band:       0180-0198z · datamodel/dm-views-rls · AUTHORED, allocated by
--             verticals/mainline/db/migrations.allocation.toml (MR-6 lock 1)
-- statements: 1
-- matrix:     verticals/mainline/db/RLS-MATRIX.yaml — this file is a RENDERING of one entry
--             there; tests/integration/schema/test_mi_rls.py asserts the two agree
-- source:     ARCHITECTURE.md §11.3 (RLS, SEC-1) · §4.1 law 10 · correction S22 · §16 MI01 · §3.2 I01 · §11.6
-- requires:   0066 mainline.disposition · 0180 peer_visible · 0185 ENABLE · 0185a FORCE
-- sqlstate:   42501 on any DELETE, from any role.
-- forward-only; no .down.sql exists at or below the protected floor.
--
-- ────────────────────────────────────────────────────────────────────────────
-- THREE LAYERS, AND THIS ONE SURVIVES A GRANT TYPED BY MISTAKE
-- ────────────────────────────────────────────────────────────────────────────
-- I01 names its three mechanisms in one line: 'revoked grants + RESTRICTIVE RLS USING
-- (false) + unconditional RAISE + no row-level TTL'. GRANTS.yaml's final denial removes
-- DELETE from every role in the matrix; the append-only trigger raises P0001; this policy
-- is the layer that still holds after somebody runs `GRANT DELETE ON mainline.disposition
-- TO …`. It does not hold against an admin, and SEC-1 says so plainly — the ledger is that
-- control.
--
-- ────────────────────────────────────────────────────────────────────────────
-- NO ROW-LEVEL TTL, EITHER, AND THAT IS A SEPARATE ASSERTION
-- ────────────────────────────────────────────────────────────────────────────
-- Row-level TTL exists on exactly three tables in the deployment and none is in schema
-- `mainline`. That is asserted by the migration suite, not by this policy, because a TTL
-- delete is issued as a regular DELETE and would be refused here — but relying on that
-- would be relying on a side effect. The Crimes (Document Destruction) Act 2006 (Vic) is
-- the reason both assertions exist separately.
--

CREATE POLICY disposition_delete_never ON mainline.disposition
  AS RESTRICTIVE FOR DELETE TO PUBLIC
  USING (false);

