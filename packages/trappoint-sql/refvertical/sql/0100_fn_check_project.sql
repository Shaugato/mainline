-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: Apache-2.0
--
-- TRAPPOINT_REF · 0100_fn_check_project.sql
-- CREATE FUNCTION trappoint_ref.fn_check_project — severity and virulence are projections, never inputs
--
-- MI: MI25, MI01
-- I: I02
-- COUNSEL-GATED: no
-- RATIONALE: Finding S1: the flagship claim was launderable one hop upstream, because an
--            LLM-driven role that could write a blocking check could choose its virulence
--            class and the clearance lattice would then enforce a claim the writer made
--            about itself. This function overwrites severity, virulence and closure_gen
--            from the blame closure regardless of what the inserter supplied, and refuses
--            with P0001 when no closure row exists. Absence of evidence refuses; it never
--            defaults.
--
-- @rendered-by  trappoint render
-- @template     packages/trappoint-sql/templates/0100_fn_check_project.sql.j2
-- @binding      packages/trappoint-sql/refvertical/vertical.toml
-- DO NOT EDIT. `trappoint render --check` is a zero-diff assertion in CI, so a
-- hand edit here is a red build, not a silent divergence.
--
-- migration:  0100_fn_check_project
-- band:       0100-0109z · kernel/projection-triggers · RENDERED
--             Allocated by verticals/mainline/db/migrations.allocation.toml (MR-6 lock 1).
-- statements: 1
-- invariants: MI25 — blocking_check.severity and .virulence are projections of the blame
--             closure, never inputs; raising on a missing closure is the whole of it.
-- source:     ARCHITECTURE.md §5.11 item 1 · §2.2 S1 · §16 MI25 ·
--             spec/binding/authority-source.md §4 (this emission is normative there)
-- requires:   trappoint_ref.clause_blame_current (the binding's declared authority relation) ·
--             trappoint_ref.blocking_check (migration 0058, RENDERED, kernel
--             `obligation-and-clearance`) · trappoint_ref.virulence_class (0013)
-- provides:   trappoint_ref.fn_check_project() — welded to blocking_check by 0120
-- sqlstate:   P0001 when the closure lookup misses. NEVER a synthetic 23514/23503/23505:
--             spec/errors.md §3.3 bans a synthetic constraint-backed code, because it produces
--             an exhibit nobody can name.
-- forward-only; no .down.sql exists at or below the protected floor, and under MR-5 no
--             .up.sql either.
--
-- THE CONTRACT LINES BELOW ARE MACHINE-READABLE. `trappoint render --check` and the migration
-- linter read them to confirm the committed SQL still corresponds to the declaration that
-- produced it, so they are not decoration and they are not free-text.
--
-- @projects blocking_check.severity, blocking_check.virulence, blocking_check.closure_gen
-- @authority trappoint_ref.clause_blame_current (clause_uuid, as_of_commit) <= NEW (clause_uuid, commit_id)
-- @on_missing raise
--
-- WHAT A REVIEWER SHOULD CHECK, IN ORDER:
--   (a) there is no `IF … IS NULL` guard around the assignments — the overwrite is total;
--   (b) the RAISE is P0001 and its message begins 'TRAPPOINT_REF: ';
--   (c) nothing in the body reads a column of the row being inserted except the lookup key.
--       The projected columns are WRITE-ONLY here. If a future edit ever reads
--       `(NEW).severity`, P-2 is broken and the render contract cannot see it.
--
-- ACYCLICITY. BEFORE INSERT on blocking_check, writing only to NEW. It reads one relation it
-- can never write. Trigger depth contributed: 0.

CREATE FUNCTION trappoint_ref.fn_check_project() RETURNS TRIGGER LANGUAGE PLpgSQL AS $$
DECLARE
  v_severity INT2;
  v_virulence trappoint_ref.virulence_class;
  v_closure_gen INT8;
BEGIN
  -- The authority read. One row, addressed by the declared key, from a relation the role that
  -- writes blocking_check may not write (rule A-6, asserted structurally at render time and by
  -- privilege probe at migration time).
  SELECT c.max_severity, c.virulence, c.closure_gen
    INTO v_severity, v_virulence, v_closure_gen
    FROM trappoint_ref.clause_blame_current c
   WHERE c.clause_uuid = (NEW).clause_uuid AND c.as_of_commit = (NEW).commit_id;

  IF v_severity IS NULL THEN
    RAISE EXCEPTION USING ERRCODE='P0001',
      MESSAGE='TRAPPOINT_REF: no blame closure for this clause version — cannot arm a check';
  END IF;

  -- UNCONDITIONAL. A supplied value is overwritten whether or not it agrees.
  NEW.severity := v_severity;
  NEW.virulence := v_virulence;
  NEW.closure_gen := v_closure_gen;
  RETURN NEW;
END $$;
