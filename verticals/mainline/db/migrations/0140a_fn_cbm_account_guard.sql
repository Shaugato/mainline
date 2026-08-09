-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- MAINLINE · 0140a_fn_cbm_account_guard.sql
-- CREATE FUNCTION mainline.fn_cbm_account_guard — the projector is never trusted
--
-- MI: MI25, MI26, MI03
-- I: I02, I05
-- COUNSEL-GATED: no
-- RATIONALE: Finding S1 said the flagship claim was launderable one hop upstream, because a
--            role that could WRITE the number a gate reads could choose what the gate decided.
--            This function is that finding applied to the accounting itself. Every one of the
--            six counters on `mainline.cbm_account` is RE-DERIVED here from
--            `clause_blame_current`, `identity_assignment` and `identity_residue`, and the
--            derived value OVERWRITES whatever the inserter supplied — so an account whose
--            `carried` is inflated to make the identity close is not rejected, it is silently
--            corrected and then refused by `cbm_balances` on the corrected numbers. A projector
--            that can choose its own numerator is not a projection (P2); it is a claim wearing
--            a projection's clothes, and the claim is precisely the thing under suspicion.
--
-- migration:  0140a_fn_cbm_account_guard
-- domain:     algorithms
-- band:       0140-0144z · datamodel/dm-functions-triggers + algorithms · AUTHORED, allocated
--             by verticals/mainline/db/migrations.allocation.toml (MR-6 lock 1).
--             MR-5 BAND OVERFLOW, and deliberately so. The allocation names
--             `fn_delta_witness_guard = 0140` for this domain and
--             docs/leads/migration-chain-verification.md gives `0141`-`0144` to
--             `datamodel/dm-functions-triggers`. A worker who has run out of numbers SUFFIXES
--             ITS OWN LAST NUMBER; it never borrows a neighbour's. `0140a`-`0140c` are this
--             domain's overflow of `0140`, they sort after `0140_` and before `0141_`, and no
--             number belonging to another owner is touched. The brief's `0202` is void with the
--             rest of the `0200-0219` annexe (MR-7).
-- statements: 1  (the CREATE FUNCTION, and nothing else — the trigger is 0145a)
-- invariants: MI25 — a gate column is a projection, re-derived from the closure, never an input.
--             MI26 — generation-dense and monotone; a correction is a new generation.
--             MI03 — the count this arithmetic stands behind.
--             I02, I05.
-- source:     docs/leads/algorithms.md §5 (PROJECT) · ARCHITECTURE.md §5.11 fn_check_project
--             (the style and the fail-closed shape this copies) · §5.4 · §16 MI25/MI26.
-- requires:   0024 mainline.commit_obj · 0025 mainline.commit_edge · 0029 mainline.clause_version
--             · 0049 mainline.identity_residue · 0049b mainline.identity_assignment (W8)
--             · 0049c mainline.cbm_account · mainline.clause_blame_current (dm-blame, 0032-0039)
--             ALL SIX must exist before this statement applies: CockroachDB resolves a PL/pgSQL
--             body's table references at CREATE FUNCTION time, so a missing dependency is a
--             migration failure here and not a runtime surprise later.
-- attached by: 0145a_trg_cbm_account_guard.sql. This function does nothing until that trigger
--             exists, and that trigger cannot exist until this function does.
-- sqlstate:   P0001, three times, with three distinct messages. Nothing else.
-- forward-only; no .down.sql exists at or below the protected floor (DM-14).
--
-- ═════════════════════════════════════════════════════════════════════════════════════════════
-- GT-A1 — WHAT WAS OBSERVED ABOUT TRIGGER FIRING ORDER, AND WHY NOTHING HERE USES IT
-- ═════════════════════════════════════════════════════════════════════════════════════════════
-- Decision D10: no trigger in this domain depends on inter-trigger firing order. CockroachDB
-- v26.2 does not document the order in which several row-level triggers on one table fire, and
-- PL-3 forbids a dated path resting on an unproven capability.
--
-- OBSERVED on CockroachDB CCL v26.2.5, 2026-08-09, on the machine this file was authored on:
-- `mainline.cbm_account` carries exactly ONE `BEFORE INSERT` trigger, so no order exists to
-- observe on it; on a two-trigger probe table the observed order matched creation order, and
-- THAT OBSERVATION IS RECORDED HERE AND USED NOWHERE. This function reads no column that any
-- other trigger writes: it reads `(NEW).commit_id` and `(NEW).account_gen`, both supplied by
-- the INSERT itself, and everything else comes from other tables. Whatever fires around it, its
-- answer is the same.
--
-- ═════════════════════════════════════════════════════════════════════════════════════════════
-- THE DERIVATION, STATED ONCE, PRECISELY, SO THE PYTHON CAN BE COMPARED AGAINST IT
-- ═════════════════════════════════════════════════════════════════════════════════════════════
-- `mainline_domain.cbm.account.derive_account` implements exactly this and
-- `tests/integration/algorithms/cbm/test_differential_200.py` proves the two agree on 200
-- fixture commits. If the two ever disagree, THIS file is right, because this one is the one a
-- state transition is conditioned on.
--
--     FP(c)  the FIRST PARENT of c: commit_edge WHERE child_id = c AND parent_ord = 0.
--            A root commit has none; then A(c) is empty and every counter is 0, which is
--            correct — a commit with no ancestry inherits no obligations.
--     D(c)   the TOUCHED DOCUMENTS of c: DISTINCT doc_id over clause_version WHERE commit_id = c.
--     A(c)   the BLOOD-BEARING ANCESTORS: clause_uuid over clause_version at FP(c) whose doc_id
--            is in D(c) and whose clause_blame_current row at as_of_commit = FP(c) has
--            max_severity >= 4.
--
--     inherited = |A(c)|
--
-- and each ancestor in A(c) is placed in exactly ONE bucket by this precedence, which is
-- fail-closed at every step:
--
--     1 residue_open       any identity_residue row for (c, ancestor) with disposition_id NULL
--     2 residue_disposed   an identity_residue row exists and every one is dispositioned
--     3 split_carried      no residue; an identity_assignment row with relation 'split'
--     4 merge_carried      no residue, no split; an assignment with relation 'merge'
--     5 carried            no residue, no split, no merge; an assignment with relation 'matched'
--
-- An ancestor in NONE of the five is UNACCOUNTED. It is not an error here — this function
-- reports what it found — and the sum is then strictly less than `inherited`, so
-- `CONSTRAINT cbm_balances` refuses the row with `23514`. That is the whole mechanism: the
-- refusal is arithmetic, not a rule someone wrote down.
--
-- WHY THE BUCKETS COUNT ANCESTORS AND NOT ROWS. `identity_residue`'s UNIQUE key is
-- (commit_id, ancestor_clause_uuid, REASON), and its own migration says at length that one
-- ancestor may legitimately be both `ambiguous` and `anchor_drop`. `identity_assignment` is
-- keyed over the descendant too, so a split writes one row per child. Counting rows would make
-- the right-hand side exceed the left on perfectly ordinary data and the identity would be
-- arithmetic about nothing. The two `GROUP BY ancestor_clause_uuid` CTEs below are what makes
-- the law a law.
--
-- WHY 'absent' IS NOT A BUCKET. `identity_assignment.relation` admits 'absent', and an absent
-- ancestor is exactly the case the conservation law says must be EXPLICITLY absent with a
-- signed disposition. An 'absent' assignment with no residue row is therefore an assertion with
-- no obligation attached, and it counts as nothing — which makes the account unbalanced and the
-- write refused. Declaring an obligation gone is not the same as recording that it is gone.
--
-- ═════════════════════════════════════════════════════════════════════════════════════════════
-- THE THREE REFUSALS
-- ═════════════════════════════════════════════════════════════════════════════════════════════
--   MAINLINE: cbm account refused — the commit it accounts for does not exist
--       The FK on 0049c would also refuse a fabricated commit, but `site_id` is derived from
--       that commit and a derivation cannot proceed from a missing source. Absence of the
--       authority row REFUSES; it does not default (P2).
--
--   MAINLINE: cbm account refused — blame closure not materialised for the first-parent commit
--       MI22's shape, applied here. `inherited` is a fact about severity, severity lives in the
--       closure, and a closure that has not been projected yet is not a severity of zero. The
--       check is over EVERY clause version in the first-parent commit within the touched
--       documents, not only the blood-bearing ones, because which ones are blood-bearing is
--       exactly what a missing closure row prevents us from knowing.
--
--   MAINLINE: cbm account generations must be dense and monotone
--       `fn_closure_guard`'s rule (MI26), applied to the account. Without it a projector could
--       re-file an old, favourable generation on top of a newer, damning one, and the newest
--       generation is what `z_cbm_gate` and `v_cbm_ledger` read.
--
-- ═════════════════════════════════════════════════════════════════════════════════════════════
-- PLATFORM NOTES — MEASURED ON v26.2.5, 2026-08-09, EACH ONE COST A FAILING STATEMENT
-- ═════════════════════════════════════════════════════════════════════════════════════════════
-- (a) READING a trigger pseudo-record column REQUIRES parentheses: `(NEW).commit_id`. The
--     unparenthesised form parses inside the function body and then fails at CREATE TRIGGER
--     time with `42P01 no data source matches prefix: new in this context` — i.e. the function
--     applies, the attachment does not, and the diagnosis is one migration downstream of the
--     defect. See go.crdb.dev/issue-v/114687/v26.2.
-- (b) WRITING one REQUIRES NO parentheses: `NEW.site_id := ...`. `(NEW).site_id := ...` is
--     `42601 syntax error at or near "("`. The two forms are opposite and both are load-bearing;
--     this file uses `(NEW).x` to read and `NEW.x :=` to write, which is the only combination
--     that applies AND attaches.
-- (c) A leading `WITH` on a `SELECT ... INTO`, `count(*) FILTER (WHERE ...)`, `bool_or()` and
--     `LEFT JOIN` inside a PL/pgSQL body all work (CTEs in UDFs stopped being a limitation in
--     v25.1). The nine-way classification below is therefore ONE statement.
-- (d) Style (ARCHITECTURE.md §5.11): PL/pgSQL, row-level, no `FOR..IN`, no `FOREACH`, no
--     `EXECUTE`, no `PERFORM`, no PL/pgSQL `CASE`; `IF`/`ELSIF` plus scalar `SELECT .. INTO`.
--     The `FILTER` predicates below are SQL expressions inside one aggregate query, not control
--     flow, which is why the buckets need no `CASE` and no loop.

CREATE FUNCTION mainline.fn_cbm_account_guard() RETURNS TRIGGER LANGUAGE PLpgSQL AS $$
DECLARE
  cid          BYTES;
  fp           BYTES;
  owning_site  UUID;
  prev_gen     INT8;
  n_no_closure INT8;
  n_inherited  INT8;
  n_carried    INT8;
  n_split      INT8;
  n_merge      INT8;
  n_open       INT8;
  n_disposed   INT8;
BEGIN
  cid := (NEW).commit_id;

  -- 1. THE AUTHORITY FOR site_id. Absence refuses; it does not default.
  SELECT c.site_id INTO owning_site
    FROM mainline.commit_obj c
   WHERE c.commit_id = cid;

  IF owning_site IS NULL THEN
    RAISE EXCEPTION USING ERRCODE='P0001',
      MESSAGE='MAINLINE: cbm account refused — the commit it accounts for does not exist';
  END IF;

  -- 2. THE BASELINE. NULL for a root commit, which makes every counter below 0.
  SELECT e.parent_id INTO fp
    FROM mainline.commit_edge e
   WHERE e.child_id = cid
     AND e.parent_ord = 0;

  -- 3. MI26: dense and monotone generations.
  SELECT max(a.account_gen) INTO prev_gen
    FROM mainline.cbm_account a
   WHERE a.site_id = owning_site
     AND a.commit_id = cid;

  IF prev_gen IS NULL AND (NEW).account_gen <> 0 THEN
    RAISE EXCEPTION USING ERRCODE='P0001',
      MESSAGE='MAINLINE: cbm account generations must be dense and monotone';
  END IF;

  IF prev_gen IS NOT NULL AND (NEW).account_gen <> prev_gen + 1 THEN
    RAISE EXCEPTION USING ERRCODE='P0001',
      MESSAGE='MAINLINE: cbm account generations must be dense and monotone';
  END IF;

  -- 4. FAIL CLOSED ON AN UNMATERIALISED CLOSURE. A severity nobody has projected yet is not a
  --    severity of zero, and a zero here would silently shrink `inherited` — which is a gate
  --    that opens.
  SELECT count(*) INTO n_no_closure
    FROM mainline.clause_version pv
   WHERE pv.commit_id = fp
     AND pv.doc_id IN (SELECT DISTINCT tv.doc_id
                         FROM mainline.clause_version tv
                        WHERE tv.commit_id = cid)
     AND NOT EXISTS (SELECT 1
                       FROM mainline.clause_blame_current c
                      WHERE c.clause_uuid = pv.clause_uuid
                        AND c.as_of_commit = fp);

  IF n_no_closure > 0 THEN
    RAISE EXCEPTION USING ERRCODE='P0001',
      MESSAGE='MAINLINE: cbm account refused — blame closure not materialised for the first-parent commit';
  END IF;

  -- 5. THE CONSERVATION IDENTITY, RE-DERIVED. One statement, five buckets, no tie-break.
  WITH touched AS (
    SELECT DISTINCT tv.doc_id AS doc_id
      FROM mainline.clause_version tv
     WHERE tv.commit_id = cid
  ),
  anc AS (
    SELECT DISTINCT pv.clause_uuid AS cu
      FROM mainline.clause_version pv
      JOIN touched t
        ON t.doc_id = pv.doc_id
      JOIN mainline.clause_blame_current c
        ON c.clause_uuid = pv.clause_uuid
       AND c.as_of_commit = fp
     WHERE pv.commit_id = fp
       AND c.max_severity >= 4
  ),
  res AS (
    SELECT r.ancestor_clause_uuid AS cu,
           bool_or(r.disposition_id IS NULL) AS r_open
      FROM mainline.identity_residue r
     WHERE r.commit_id = cid
     GROUP BY r.ancestor_clause_uuid
  ),
  asg AS (
    SELECT g.ancestor_clause_uuid AS cu,
           bool_or(g.relation = 'split')   AS a_split,
           bool_or(g.relation = 'merge')   AS a_merge,
           bool_or(g.relation = 'matched') AS a_match
      FROM mainline.identity_assignment g
     WHERE g.commit_id = cid
     GROUP BY g.ancestor_clause_uuid
  )
  SELECT count(*),
         count(*) FILTER (WHERE r.cu IS NULL
                            AND NOT coalesce(g.a_split, false)
                            AND NOT coalesce(g.a_merge, false)
                            AND coalesce(g.a_match, false)),
         count(*) FILTER (WHERE r.cu IS NULL
                            AND coalesce(g.a_split, false)),
         count(*) FILTER (WHERE r.cu IS NULL
                            AND NOT coalesce(g.a_split, false)
                            AND coalesce(g.a_merge, false)),
         count(*) FILTER (WHERE coalesce(r.r_open, false)),
         count(*) FILTER (WHERE r.cu IS NOT NULL
                            AND NOT coalesce(r.r_open, false))
    INTO n_inherited, n_carried, n_split, n_merge, n_open, n_disposed
    FROM anc a
    LEFT JOIN res r ON r.cu = a.cu
    LEFT JOIN asg g ON g.cu = a.cu;

  -- 6. OVERWRITE. Not "validate against" — OVERWRITE. A projector that supplied a different
  --    number learns nothing from this write except that the database disagreed, which is the
  --    only feedback a component under suspicion is entitled to.
  NEW.site_id          := owning_site;
  NEW.wrote_as         := current_user;
  NEW.inherited        := n_inherited;
  NEW.carried          := n_carried;
  NEW.split_carried    := n_split;
  NEW.merge_carried    := n_merge;
  NEW.residue_open     := n_open;
  NEW.residue_disposed := n_disposed;

  RETURN NEW;
END $$;
