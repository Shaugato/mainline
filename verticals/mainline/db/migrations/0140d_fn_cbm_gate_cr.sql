-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- MAINLINE · 0140d_fn_cbm_gate_cr.sql
-- CREATE FUNCTION mainline.fn_cbm_gate_cr — the document branch is gated on the same arithmetic
--
-- MI: MI30, MI03, MI22
-- I: I02
-- COUNSEL-GATED: no
-- RATIONALE: The change request is a gated subject in exactly the sense the permit is, and that
--            identity is the thesis: the repository is the protected branch and the permit is
--            one of its refs (finding S16). A conservation law that held over work permits and
--            not over document merges would be a law with a documented way around it — edit the
--            procedure instead of working under it. The messages are byte-identical to
--            `fn_cbm_gate_permit`'s because the FACT is identical; only the relation the scope
--            is read from differs.
--
-- migration:  0140d_fn_cbm_gate_cr
-- domain:     algorithms
-- band:       0140-0144z · datamodel/dm-functions-triggers + algorithms · AUTHORED, allocated
--             by verticals/mainline/db/migrations.allocation.toml (MR-6 lock 1). MR-5 band
--             overflow of this domain's own `0140`; `0141`-`0144` belong to
--             `datamodel/dm-functions-triggers` and are untouched.
-- statements: 1  (the CREATE FUNCTION — the trigger is 0145d)
-- invariants: MI30 — a change_request merges only with its obligations discharged.
--             MI03, MI22.
-- source:     docs/leads/algorithms.md §5 · ARCHITECTURE.md §5.11 fn_cr_merge_gate · §16 MI30.
-- requires:   0049 mainline.identity_residue · 0049c mainline.cbm_account ·
--             0051 mainline.change_request · 0053 mainline.cr_clause
-- attached by: 0145d_trg_cbm_gate_cr.sql, as `z_cbm_gate_cr`
-- sqlstate:   P0001, twice, with the same two messages `fn_cbm_gate_permit` raises.
-- forward-only; no .down.sql exists at or below the protected floor (DM-14).
--
-- ═════════════════════════════════════════════════════════════════════════════════════════════
-- WHY TWO FUNCTIONS AND NOT ONE WITH `TG_TABLE_NAME`
-- ═════════════════════════════════════════════════════════════════════════════════════════════
-- One function switching on `TG_TABLE_NAME` would be shorter and would rest on a PL/pgSQL
-- special variable this deployment has not verified on CockroachDB v26.2, inside a gate. PL-3
-- forbids a dated path resting on an unproven capability, and the cost of the honest version is
-- one file. It is also not really duplication: the two subjects declare their scope through
-- DIFFERENT relations with DIFFERENT key columns — `permit_clause (permit_id, …)` versus
-- `cr_clause (cr_id, …)` — so a merged function would contain both queries anyway, plus a
-- branch that decides which one to run.
--
-- The two files must be read together. If a refusal message here ever drifts from
-- `0140c_fn_cbm_gate_permit.sql`, the exhibit becomes "the database said something slightly
-- different depending on which branch you merged", which is the kind of detail that ends a
-- cross-examination badly.
--
-- ── WHAT "CITED" MEANS HERE ──────────────────────────────────────────────────────────────────
-- `cr_clause` pins the change request's scope to exact clause versions with relations
-- `edits` / `introduces` / `retires`. The distinct `commit_id`s across those rows are the
-- commits the change request is answerable to. `introduces` is included deliberately and is not
-- an oversight: a commit that introduces a clause still touches documents that carry
-- blood-bearing ancestors, and the accounting for that commit is exactly what proves the
-- introduction did not quietly displace one of them.
--
-- ── REFUSAL DEPTH, HONESTLY ──────────────────────────────────────────────────────────────────
-- Depth 1, for the same reason `0140c` gives at length: `change_request.unbalanced_cbm_count`
-- with `CONSTRAINT cbm_balanced_when_issued` would be the structural second layer, and
-- `mainline.change_request` is RENDERED SUBSTRATE (allocation band 0050-0053, mode `rendered`),
-- so that column is a template change agreed with `kernel/subject-and-pin` and re-rendered into
-- both bindings — never an `ALTER` typed into the vertical. Not done by this worker, not
-- claimed by this worker, recorded in `novelty/cbm-ledger.yaml` under `unverified`.
--
-- ── D10 ──────────────────────────────────────────────────────────────────────────────────────
-- `mainline.change_request` also carries the kernel's `cr_merge_gate`. This function reads only
-- `(NEW).cr_id` and other tables, so its answer does not depend on what fires around it.

CREATE FUNCTION mainline.fn_cbm_gate_cr() RETURNS TRIGGER LANGUAGE PLpgSQL AS $$
DECLARE
  rid      UUID;
  n_absent INT8;
  n_stale  INT8;
BEGIN
  rid := (NEW).cr_id;

  SELECT count(*) INTO n_absent
    FROM (SELECT DISTINCT cc.commit_id AS commit_id
            FROM mainline.cr_clause cc
           WHERE cc.cr_id = rid) cited
   WHERE NOT EXISTS (SELECT 1
                       FROM mainline.cbm_account a
                      WHERE a.commit_id = cited.commit_id);

  IF n_absent > 0 THEN
    RAISE EXCEPTION USING ERRCODE='P0001',
      MESSAGE='MAINLINE: merge refused — blame accounting absent for a cited commit';
  END IF;

  WITH cited AS (
    SELECT DISTINCT cc.commit_id AS commit_id
      FROM mainline.cr_clause cc
     WHERE cc.cr_id = rid
  ),
  newest AS (
    SELECT DISTINCT ON (a.commit_id)
           a.commit_id    AS commit_id,
           a.residue_open AS residue_open
      FROM mainline.cbm_account a
      JOIN cited x ON x.commit_id = a.commit_id
     ORDER BY a.commit_id, a.account_gen DESC
  ),
  live AS (
    SELECT r.commit_id AS commit_id,
           count(DISTINCT r.ancestor_clause_uuid) AS n_open
      FROM mainline.identity_residue r
      JOIN cited y ON y.commit_id = r.commit_id
     WHERE r.disposition_id IS NULL
     GROUP BY r.commit_id
  )
  SELECT count(*) INTO n_stale
    FROM newest n
    LEFT JOIN live l ON l.commit_id = n.commit_id
   WHERE n.residue_open <> coalesce(l.n_open, 0);

  IF n_stale > 0 THEN
    RAISE EXCEPTION USING ERRCODE='P0001',
      MESSAGE='MAINLINE: merge refused — blame accounting is stale for a cited commit';
  END IF;

  RETURN NEW;
END $$;
