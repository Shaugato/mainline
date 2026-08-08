-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- MI: MI22
-- I: I14
-- COUNSEL-GATED: no
-- RATIONALE: This function is where decision D8 stops being a policy and becomes a write precondition. A `clause_version` that declares a lattice weakening is asserting that a deterministic comparison of two Control Assertion Tuples found this edit to loosen a safety control; that claim has reasons or it has nothing, and I14 says a refusal without its irreducible reason set is one somebody routes around. The two P0001 messages below are the two exhibits — no witnesses at all, and witnesses with no minimal member — and they are distinct because a refusal that tells the writer the wrong thing costs an hour.
--
-- migration:  0140_fn_delta_witness_guard
-- domain:     algorithms
-- band:       0140-0144 · datamodel/dm-functions-triggers + algorithms · AUTHORED, allocated by
--             verticals/mainline/db/migrations.allocation.toml (MR-6 lock 1), which names
--             `fn_delta_witness_guard = 0140` in the vertical PL/pgSQL function band.
-- statements: 1  (the CREATE FUNCTION, and nothing else — see THE SPLIT, below)
-- invariants: I14  — every refusal emits an irreducible reason set (ARCHITECTURE.md §3.1).
--             MI22 — the gate fails closed on an absent projection: a lattice weakening whose
--                    explanation is missing is refused, not stored unexplained.
-- source:     docs/leads/algorithms.md D8, D10, §9 (written as the first half of 0211;
--             SPLIT AND RELOCATED to 0140 by docs/leads/migration-reconciliation.md §5.4)
--             ARCHITECTURE.md §5.3 (clause_version.control_delta / delta_basis) · §5.11 (style)
-- requires:   0029 mainline.clause_version · 0049a mainline.delta_witness
-- attached by: 0145_trg_delta_witness_guard.sql — this function does nothing until that
--             trigger exists, and that trigger cannot exist until this function does.
-- sqlstate:   P0001, twice, with two distinct messages. Nothing else.
-- forward-only; no .down.sql exists at or below the protected floor (DM-14).
--
-- ═════════════════════════════════════════════════════════════════════════════════════════════
-- THE SPLIT: WHY THIS FILE IS 0140 AND THE TRIGGER IS 0145
-- ═════════════════════════════════════════════════════════════════════════════════════════════
-- This file and `0145_trg_delta_witness_guard.sql` were one file, `0211_fn_delta_witness_guard.sql`,
-- whose own header admitted `statements: 2`. That was two violations at once.
--
-- 1. ONE STATEMENT PER FILE IS NON-NEGOTIABLE. CockroachDB DDL is not transactional across
--    statements, and the runner does not wrap a migration body in a transaction because DDL
--    inside a multi-statement transaction can fail at COMMIT even when every statement
--    succeeded. So a two-statement file is not atomic: if the CREATE FUNCTION applied and the
--    CREATE TRIGGER did not, the version is marked `dirty` and the operator cannot tell from
--    the marker which half is on the cluster. One statement makes `dirty` answerable in
--    seconds. `statement_count()` enforces it and reported this file for weeks.
--
-- 2. A FUNCTION AND A TRIGGER CANNOT BOTH BE IN THE RIGHT BAND. §18 stratifies the order —
--    tables, then functions, then triggers, then views, then policies — and 0211 was in none
--    of those strata because 0200+ was never defined by §18 at all. The algorithms 0200-0219
--    annexe is revoked (MR-7); 0200+ is UNALLOCATED and `trappoint migrate lint` rule B
--    refuses it. The function takes 0140 in the vertical function band 0140-0144 and the
--    trigger takes 0145 in the vertical trigger band 0145-0149, which is the stratification
--    §18 actually defines.
--
-- The body below is byte-for-byte the function that was verified at 0211, including both
-- P0001 messages. The split moved statements between files; it changed no SQL.
--
-- ═════════════════════════════════════════════════════════════════════════════════════════════
-- DECISION D8, AS A WRITE PRECONDITION
-- ═════════════════════════════════════════════════════════════════════════════════════════════
-- A `clause_version` that declares `control_delta IN ('weaken','remove')` on
-- `delta_basis = 'lattice'` is claiming that a deterministic, model-free comparison of two
-- Control Assertion Tuples found this edit to loosen a safety control. That claim has reasons
-- or it has nothing. This function requires the reasons to already be in the transaction.
--
-- The message is exact and is pinned by
-- `tests/integration/algorithms/lattice/test_witness_or_refuse.py`:
--
--     MAINLINE: a lattice weakening must carry its minimal witness set
--
-- ── THE ORDERING CONTRACT THIS DEPENDS ON (0049a's header states it normatively) ─────────────
--
--     BEGIN;
--       INSERT INTO mainline.delta_witness (...);   -- FIRST
--       INSERT INTO mainline.clause_version (...);  -- SECOND, and the 0145 trigger fires here
--     COMMIT;
--
-- A BEFORE INSERT trigger sees rows already written in its own transaction, so witnesses
-- inserted first are visible and witnesses inserted afterwards are not. That asymmetry IS the
-- mechanism: there is no ordering in which a version row reaches COMMIT having been checked
-- against witnesses that did not yet exist.
--
-- ── WHY THIS DOES NOT DEPEND ON TRIGGER FIRING ORDER (decision D10) ──────────────────────────
-- CockroachDB v26.2 does not document the firing order of multiple row-level triggers on one
-- table, and PL-3 forbids a dated path resting on an unproven capability. So this guard reads
-- ONLY columns the INSERT itself supplies — `control_delta`, `delta_basis`, `clause_uuid`,
-- `commit_id` — and never a column another trigger projects. Whatever order the schema lead's
-- BLOODLINE guard, `fn_weaken_materialise` and this function run in, this one's answer is the
-- same. `GT-A1` measures the observed order and records it; nothing here consults the result.
--
-- ── WHY THE GUARD MAY READ AN INSERTER-SUPPLIED COLUMN, WHEN P2 SAYS NOT TO ──────────────────
-- P2 governs columns a gate reads to decide a FACT ABOUT ANOTHER ROW — those must be projected
-- from an authoritative table, never taken from the writer. This guard decides nothing about
-- another row. It reads the writer's own CLAIM and attaches an obligation to it: *if you assert
-- a lattice weakening, you must have written its reasons*. The claim is the inserter's; the
-- obligation is the database's.
--
-- The dodge that remains, stated plainly rather than left for a reviewer to find: a writer can
-- declare `restate` on an edit that is really a weakening, and this guard will not notice,
-- because it is not the component that decides what the edit was. That dodge is caught
-- elsewhere and by arithmetic — the matcher and the CONSERVATION OF BLAME MASS ledger (workers
-- W8/W9) account for every blood-written obligation across the commit, so an evaded weakening
-- surfaces as an orphaned obligation, which is a louder gate than the one it was hiding from.
-- This file closes one hole and names the other; it does not claim both.
--
-- ── WHY `abstain_to_weaken` AND `human` ARE EXEMPT, AND `lattice+model` IS NOT ───────────────
--   'abstain_to_weaken'  THE RATCHET fires precisely when Path A could NOT decide. Demanding a
--                        lattice witness for it would demand an explanation that does not exist,
--                        and a guard that cannot be satisfied is a guard somebody disables. The
--                        arithmetic behind an abstention is written to the logged-silence ledger
--                        instead (§6.3).
--   'human'              a person overrode the machine; their explanation is the commit message
--                        and the signature on it, which `commit_obj` already carries.
--   'lattice+model'      NOT exempt. If a model raised the force of a verdict the lattice had
--                        already formed, the lattice's own reasons are still the ones the
--                        database can check — and a `lattice+model` weaken with no lattice
--                        witness is a state transition resting entirely on a model, which
--                        principle P7 does not permit.
--
-- ── THE SECOND REFUSAL: A WITNESS SET WITH NO MINIMAL MEMBER ─────────────────────────────────
-- I14 asks for an IRREDUCIBLE reason set, not a pile. `mainline.delta_witness.minimal` marks
-- the members of the minimal unsatisfiable subset, and a weakening whose witnesses are all
-- flagged non-minimal has supplied a repair list with no reason in it. That is a distinct
-- defect from having no witnesses at all, so it gets a distinct message rather than being
-- folded into the first one — a refusal that tells the writer the wrong thing costs an hour.
-- Because `minimal` defaults to `true`, a writer that never heard of the column cannot trip
-- this; only one that explicitly set every row `false` can.
--
-- ── PLATFORM NOTES ───────────────────────────────────────────────────────────────────────────
-- (a) CockroachDB requires `OLD`/`NEW` to be PARENTHESISED when a column is read —
--     `(NEW).control_delta`, not `NEW.control_delta`. A documented known limitation whose own
--     v26.2 examples read `(NEW).wage`. ARCHITECTURE §5.11 is written in the unparenthesised
--     PostgreSQL style and every trigger in this deployment needs the correction.
-- (b) The enum comparison is written with explicit `::mainline.control_delta` casts rather than
--     relying on literal-to-enum inference inside a PL/pgSQL `IN` list. The inference is
--     standard PostgreSQL behaviour and is very likely fine; an explicit cast costs one token
--     and removes the question, which is the right trade under a gate.
-- (c) Style (§5.11): PL/pgSQL, row-level, no FOR..IN, no FOREACH, no EXECUTE, no PERFORM, no
--     CASE; IF/ELSIF plus scalar aggregate SELECT..INTO.
--
-- ── NAME COLLISION, DELIBERATELY AVOIDED ─────────────────────────────────────────────────────
-- The schema lead owns `clause_version_guard` on this same table (the BLOODLINE / MI15 guard,
-- bands 0140-0149). This function is `mainline.fn_delta_witness_guard` and the trigger 0145
-- attaches is `z_delta_witness_required`; neither name is theirs, and the `z_` prefix follows
-- the convention `z_cbm_gate` sets in docs/leads/algorithms.md §5 for a guard that is
-- deliberately order-independent.

CREATE FUNCTION mainline.fn_delta_witness_guard() RETURNS TRIGGER LANGUAGE PLpgSQL AS $$
DECLARE
  n_witness INT8;
  n_minimal INT8;
BEGIN
  IF (NEW).delta_basis NOT IN ('lattice', 'lattice+model') THEN
    RETURN NEW;
  END IF;

  IF (NEW).control_delta NOT IN
       ('weaken'::mainline.control_delta, 'remove'::mainline.control_delta) THEN
    RETURN NEW;
  END IF;

  SELECT count(*) INTO n_witness
    FROM mainline.delta_witness dw
   WHERE dw.clause_uuid = (NEW).clause_uuid
     AND dw.commit_id   = (NEW).commit_id;

  IF n_witness = 0 THEN
    RAISE EXCEPTION USING ERRCODE='P0001',
      MESSAGE='MAINLINE: a lattice weakening must carry its minimal witness set';
  END IF;

  SELECT count(*) INTO n_minimal
    FROM mainline.delta_witness dw
   WHERE dw.clause_uuid = (NEW).clause_uuid
     AND dw.commit_id   = (NEW).commit_id
     AND dw.minimal;

  IF n_minimal = 0 THEN
    RAISE EXCEPTION USING ERRCODE='P0001',
      MESSAGE='MAINLINE: a lattice weakening carries witnesses but none is minimal — I14 asks for an irreducible reason set, not a repair list';
  END IF;

  RETURN NEW;
END $$;
