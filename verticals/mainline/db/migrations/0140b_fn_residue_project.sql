-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- MAINLINE · 0140b_fn_residue_project.sql
-- CREATE FUNCTION mainline.fn_residue_project — closing the P2 hole the architecture annotated
-- and never filled
--
-- MI: MI25, MI03, MI22
-- I: I02
-- COUNSEL-GATED: no
-- RATIONALE: `mainline.identity_residue.max_ancestral_severity` is annotated `PROJECTED from
--            clause_blame_closure (P2)` in ARCHITECTURE.md §5.3, and §5.11 lists no trigger
--            that projects it — only `fn_residue_counter`, which counts. Until this file, the
--            column was client-supplied, and 0049's own header says so plainly rather than
--            implying a control that did not exist. That gap is not cosmetic: the column
--            decides HOW HARD the residue row bites. `mainline.clearance_legal` has three
--            deliberately absent cells — `mechanism_absent` and `accept_residual` are not legal
--            verdicts over blood-fatal ancestry — so a writer who could lower this number could
--            convert an undischargeable obligation into a discharge­able one and dispose of it.
--            The whole flagship claim rests on a matcher failure becoming a LOUDER gate; a
--            self-declared severity is the one edit that makes it a quieter one.
--
-- migration:  0140b_fn_residue_project
-- domain:     algorithms
-- band:       0140-0144z · datamodel/dm-functions-triggers + algorithms · AUTHORED, allocated
--             by verticals/mainline/db/migrations.allocation.toml (MR-6 lock 1). MR-5 band
--             overflow of this domain's own `0140`; `0141`-`0144` are dm-functions-triggers'
--             and are untouched. The brief's `0204` is void with the `0200-0219` annexe (MR-7).
-- statements: 1  (the CREATE FUNCTION — the trigger is 0145b)
-- invariants: MI25 — severity is a projection of the blame closure, never an input.
--             MI22 — the gate fails closed on an absent projection.
--             MI03 — the refusal this severity modulates.
-- source:     docs/leads/algorithms.md §4 ("`max_ancestral_severity` is a projection, not an
--             input … This is a P2 hole and this domain closes it") · ARCHITECTURE.md §5.3 ·
--             §5.11 · §16 MI25.
-- requires:   0025 mainline.commit_edge · 0049 mainline.identity_residue ·
--             mainline.clause_blame_current (dm-blame, band 0032-0039)
-- attached by: 0145b_trg_residue_project.sql
-- sqlstate:   P0001, twice, with two distinct messages. Nothing else.
-- forward-only; no .down.sql exists at or below the protected floor (DM-14).
--
-- ═════════════════════════════════════════════════════════════════════════════════════════════
-- WHY THE FIRST PARENT, AND NOT THE COMMIT ITSELF
-- ═════════════════════════════════════════════════════════════════════════════════════════════
-- A residue row says: *this ancestor obligation is missing from commit c*. The severity that
-- matters is therefore the one the obligation carried BEFORE the edit — in the commit the edit
-- was made against — not one read from a state the edit produced. Reading the severity from `c`
-- would let the same commit that dropped the control also decide how serious dropping it was.
-- `commit_edge.parent_ord = 0` is the first parent, which 0025 defines as the mainline; a merge
-- commit's second parent is a different lineage and is not the baseline this obligation was
-- inherited along.
--
-- ── DM-9: THE VIEW IS THE SOLE READ PATH ─────────────────────────────────────────────────────
-- This function names `mainline.clause_blame_current` and never `clause_blame_closure`
-- underneath it. `max(closure_gen)` discipline has to be structural — one forgotten call site
-- reads a superseded generation, and a superseded generation is a LOWER severity, which is a
-- gate that opens. `scripts/grep_closure_readpath.py` reads comments as well as code, which is
-- why the rule is honoured in this prose too.
--
-- ── THE TWO REFUSALS, AND WHY THEY ARE TWO ───────────────────────────────────────────────────
--   MAINLINE: residue refused — the commit has no first parent, so no ancestor can be missing
--       A root commit inherits nothing. A residue row against it is not a serious claim; it is
--       a malformed one, and it is refused before the closure is consulted so that the operator
--       is told the true defect rather than "no closure row".
--
--   MAINLINE: residue refused — no blame closure for the ancestor clause in the first-parent commit
--       The fail-closed case, and the expensive one to get wrong. It means the closure
--       projector has not caught up, or the ancestor was never versioned in the first-parent
--       commit at all. Either way the severity is UNKNOWN, and P3 says unknown is not zero.
--
-- A CONSEQUENCE THIS FILE OWNS AND DOES NOT HIDE: the closure projector must materialise a row
-- for (clause_uuid, as_of_commit = first parent) before any residue over that ancestor can be
-- written. That is a real ordering obligation on the projector fleet and it is the same one
-- `fn_permit_merge_gate` already imposes at merge time ("blame closure not materialised for
-- cited clauses"). This file moves the same demand earlier, to the moment the doubt is
-- recorded, where the operator can still do something about it.
--
-- ── PLATFORM NOTES (measured on CockroachDB CCL v26.2.5, 2026-08-09) ─────────────────────────
-- READ `(NEW).col` with parentheses — the unparenthesised form applies here and then fails at
-- CREATE TRIGGER with `42P01 no data source matches prefix: new`. WRITE `NEW.col := …` WITHOUT
-- them — `(NEW).col := …` is `42601`. The two forms are opposite; this file uses both correctly
-- and 0145b is the statement that proves it.
-- Style (§5.11): PL/pgSQL, row-level, no loops, no EXECUTE, one scalar `SELECT .. INTO` per
-- source.

CREATE FUNCTION mainline.fn_residue_project() RETURNS TRIGGER LANGUAGE PLpgSQL AS $$
DECLARE
  fp  BYTES;
  sev INT2;
BEGIN
  SELECT e.parent_id INTO fp
    FROM mainline.commit_edge e
   WHERE e.child_id = (NEW).commit_id
     AND e.parent_ord = 0;

  IF fp IS NULL THEN
    RAISE EXCEPTION USING ERRCODE='P0001',
      MESSAGE='MAINLINE: residue refused — the commit has no first parent, so no ancestor can be missing';
  END IF;

  SELECT c.max_severity INTO sev
    FROM mainline.clause_blame_current c
   WHERE c.clause_uuid = (NEW).ancestor_clause_uuid
     AND c.as_of_commit = fp;

  IF sev IS NULL THEN
    RAISE EXCEPTION USING ERRCODE='P0001',
      MESSAGE='MAINLINE: residue refused — no blame closure for the ancestor clause in the first-parent commit';
  END IF;

  -- OVERWRITE. Whatever the matcher supplied for this column is discarded unread: the column is
  -- a projection of the closure and the matcher is not the closure.
  NEW.max_ancestral_severity := sev;

  RETURN NEW;
END $$;
