-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- MAINLINE · 0140c_fn_cbm_gate_permit.sql
-- CREATE FUNCTION mainline.fn_cbm_gate_permit — a merge whose blame accounting is absent or
-- stale is refused
--
-- MI: MI03, MI22, MI25
-- I: I02
-- COUNSEL-GATED: no
-- RATIONALE: `cbm_balances` (0049c) refuses an account that does not balance, which means the
--            only accounts that exist are correct ones. It says nothing about a merge for which
--            NO ACCOUNT WAS EVER WRITTEN — and "we never ran the accounting" is exactly the
--            state a projector outage, a skipped batch or a deliberate omission produces. This
--            function makes the absence of the arithmetic refuse the state transition, which is
--            the only reading of P3 that survives the projector being down. It also refuses a
--            STALE account, because an accounting that was true last week and is false now is
--            worth less than none: it looks like evidence.
--
-- migration:  0140c_fn_cbm_gate_permit
-- domain:     algorithms
-- band:       0140-0144z · datamodel/dm-functions-triggers + algorithms · AUTHORED, allocated
--             by verticals/mainline/db/migrations.allocation.toml (MR-6 lock 1). MR-5 band
--             overflow of this domain's own `0140`.
-- statements: 1  (the CREATE FUNCTION — the trigger is 0145c)
-- invariants: MI03 — a merged permit carries zero un-dispositioned identity residue. This
--                    function stands one level behind that: it refuses a merge whose residue
--                    count was never computed at all.
--             MI22 — fail closed on an absent projection.  MI25 — and on a stale one.
-- source:     docs/leads/algorithms.md §5 (REFUSE (gate)) · ARCHITECTURE.md §5.11
--             fn_permit_merge_gate (the shape this copies) · §16 MI03/MI22.
-- requires:   0049 mainline.identity_residue · 0049c mainline.cbm_account ·
--             0050 mainline.permit · 0052 mainline.permit_clause
-- attached by: 0145c_trg_cbm_gate_permit.sql, as `z_cbm_gate`
-- sqlstate:   P0001, twice, with two distinct messages. Nothing else.
-- forward-only; no .down.sql exists at or below the protected floor (DM-14).
--
-- ═════════════════════════════════════════════════════════════════════════════════════════════
-- THE TWO REFUSALS, PINNED VERBATIM
-- ═════════════════════════════════════════════════════════════════════════════════════════════
--   MAINLINE: merge refused — blame accounting absent for a cited commit
--   MAINLINE: merge refused — blame accounting is stale for a cited commit
--
-- Both are pinned by `tests/integration/algorithms/cbm/test_gate_absent_account.py` as literals
-- in the test file, in this SQL, and in the psycopg error a live cluster raises. A test that
-- read the string out of this file and compared it with itself would pass for any string,
-- including an empty one.
--
-- ── WHAT "CITED" MEANS, AND WHY IT IS `permit_clause` ────────────────────────────────────────
-- The permit's declared scope is pinned to exact clause VERSIONS: `permit_clause` carries
-- (permit_id, clause_uuid, commit_id, relation) with a composite FK onto
-- `clause_version (clause_uuid, commit_id)`. The distinct `commit_id`s on those rows are the
-- commits this permit is answerable to, and each one needs its blame arithmetic done. Using the
-- permit's merged commit instead would ask about a commit that does not exist yet at the moment
-- the gate fires.
--
-- ── WHY "STALE" IS A SECOND, SEPARATE REFUSAL ────────────────────────────────────────────────
-- `cbm_account` is append-only, so an account is a statement about the world AT THE MOMENT IT
-- WAS WRITTEN. Nothing stops the world from moving: a residue row is dispositioned, or a newly
-- discovered ancestor produces another one, and the newest account now describes a state that
-- has passed. Comparing the newest generation's `residue_open` against the live count of
-- distinct ancestors with an open residue row costs one aggregate and closes the gap between
-- "the accounting balanced" and "the accounting balanced ABOUT THIS MERGE".
--
-- The consequence is a real workflow obligation and it is stated rather than buried: AFTER the
-- last disposition is signed, the projector must write one more account generation, and the
-- merge is refused until it has. That is not friction added for its own sake — under MI03 a
-- legal merge has zero open residue on its cited commits, so the account that describes the
-- merge is necessarily an account whose `residue_open` is 0. A permit that cannot get one is a
-- permit whose obligations are not actually discharged.
--
-- ── DISTINCT ANCESTORS, NOT ROWS ─────────────────────────────────────────────────────────────
-- `count(DISTINCT r.ancestor_clause_uuid)` and not `count(*)`: `identity_residue`'s UNIQUE key
-- includes `reason`, so one ancestor legitimately produces several open rows and a row count
-- would never equal the account's ancestor count. The same reasoning is spelled out at length
-- in 0140a; the two files must agree on it or this gate fires on every correct merge.
--
-- ── REFUSAL DEPTH, HONESTLY ──────────────────────────────────────────────────────────────────
-- Depth 1 for this file, and the honesty is worth more than a larger number. The structural
-- second layer this domain WANTED is `permit.unbalanced_cbm_count` with
-- `CONSTRAINT cbm_balanced_when_issued CHECK (state <> 'merged' OR unbalanced_cbm_count = 0)`.
-- `mainline.permit` is RENDERED SUBSTRATE (allocation band 0050-0053, mode `rendered`), so that
-- column is a change to `packages/trappoint-sql/templates/0050_permit.sql.j2` agreed with
-- `kernel/subject-and-pin` and re-rendered into BOTH bindings — it is emphatically not an
-- `ALTER` typed into the vertical, and MR-1 consequence 2 is that a hand-authored twin is
-- permanently red in the worst way (CI green, deploy dead). This worker did not make that
-- change and does not claim its refusal. `novelty/cbm-ledger.yaml` records the same thing under
-- `unverified`, and `ALTER TABLE mainline.permit DISABLE TRIGGER z_cbm_gate` succeeds today.
-- What the custodian patrol makes impossible is removing the RECORD that it was disabled.
--
-- ── D10: NOTHING HERE DEPENDS ON FIRING ORDER ────────────────────────────────────────────────
-- `mainline.permit` also carries the kernel's `permit_merge_gate`. This function reads only
-- `(NEW).permit_id` — supplied by the UPDATE — and other tables. Whichever of the two fires
-- first, both answers are the same and both are refusals if either condition holds. GT-A1
-- records the observed order; nothing here consults it.
--
-- ── PLATFORM NOTES (measured on CockroachDB CCL v26.2.5, 2026-08-09) ─────────────────────────
-- The trigger's `WHEN` clause needs `(NEW).state`, parenthesised — `WHEN (NEW.state = …)` fails
-- with `42P01 no data source matches prefix: new in this context`. That is 0145c's problem and
-- is recorded there too. `DISTINCT ON`, `count(… ) FILTER`, CTEs and `LEFT JOIN` inside a
-- PL/pgSQL body all execute on v26.2.5.

CREATE FUNCTION mainline.fn_cbm_gate_permit() RETURNS TRIGGER LANGUAGE PLpgSQL AS $$
DECLARE
  pid      UUID;
  n_absent INT8;
  n_stale  INT8;
BEGIN
  pid := (NEW).permit_id;

  SELECT count(*) INTO n_absent
    FROM (SELECT DISTINCT pc.commit_id AS commit_id
            FROM mainline.permit_clause pc
           WHERE pc.permit_id = pid) cited
   WHERE NOT EXISTS (SELECT 1
                       FROM mainline.cbm_account a
                      WHERE a.commit_id = cited.commit_id);

  IF n_absent > 0 THEN
    RAISE EXCEPTION USING ERRCODE='P0001',
      MESSAGE='MAINLINE: merge refused — blame accounting absent for a cited commit';
  END IF;

  WITH cited AS (
    SELECT DISTINCT pc.commit_id AS commit_id
      FROM mainline.permit_clause pc
     WHERE pc.permit_id = pid
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
