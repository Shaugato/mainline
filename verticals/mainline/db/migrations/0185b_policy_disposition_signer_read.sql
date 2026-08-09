-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- MAINLINE · 0185b_policy_disposition_signer_read.sql
-- CREATE POLICY signer_read ON mainline.disposition — the permissive base peer_blind narrows
--
-- MI: MI08
-- I: I15
-- COUNSEL-GATED: yes
-- RATIONALE: RESTRICTIVE policies only ever narrow. With `peer_blind` alone and no
--            permissive policy for the `signer` role, the role matches nothing and the
--            default is DENY — the partition would degrade into a total blackout, and
--            nobody would report it, because a signer who sees nothing assumes there is
--            nothing to see. This policy is what `peer_blind` subtracts from.
--
-- migration:  0185b_policy_disposition_signer_read
-- domain:     datamodel / dm-views-rls
-- band:       0180-0198z · datamodel/dm-views-rls · AUTHORED, allocated by
--             verticals/mainline/db/migrations.allocation.toml (MR-6 lock 1)
-- statements: 1
-- matrix:     verticals/mainline/db/RLS-MATRIX.yaml — this file is a RENDERING of one entry
--             there; tests/integration/schema/test_mi_rls.py asserts the two agree
-- source:     ARCHITECTURE.md §11.3 (RLS, SEC-1) · §4.1 law 10 · correction S22 · v26.2 CREATE POLICY reference (permissive OR, restrictive AND)
-- requires:   0066 mainline.disposition · 0180 peer_visible · 0185 ENABLE · 0185a FORCE
-- sqlstate:   42501 — or, without this file, an empty result that looks like a clean check.
-- forward-only; no .down.sql exists at or below the protected floor.
--
-- ────────────────────────────────────────────────────────────────────────────
-- THE ORDER OF OPERATIONS, STATED ONCE
-- ────────────────────────────────────────────────────────────────────────────
-- For a given (role, command), the permissive policies are OR-ed into a visible set and
-- every restrictive policy is then AND-ed against it. `signer_read` supplies the set (every
-- row) and `peer_blind` removes from it (every row that is neither mine nor released). Two
-- files, because the runner does not wrap a file in a transaction and because each is
-- separately assertable: RLS-MATRIX.yaml's test walks them individually.
--
-- ────────────────────────────────────────────────────────────────────────────
-- WHY THE PERMISSIVE HALF IS `true` AND NOT THE PARTITION ITSELF
-- ────────────────────────────────────────────────────────────────────────────
-- Writing the partition once, as a permissive `USING (signer_sub = CURRENT_USER OR
-- peer_visible)`, would work today and would silently fail the moment a second permissive
-- SELECT policy is added for the `signer` role — the two would OR, and the partition would
-- evaporate. Expressing it restrictively makes it un-OR-around-able by construction. That
-- is why §11.3 writes it that way and why this file keeps the pair.
--

CREATE POLICY signer_read ON mainline.disposition
  AS PERMISSIVE FOR SELECT TO signer
  USING (true);

