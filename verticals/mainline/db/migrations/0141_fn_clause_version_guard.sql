-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- MI: MI15
-- I: I05
-- COUNSEL-GATED: no
-- RATIONALE: This is the O-Ring Ratchet as a write precondition. `mainline.clause_version` has carried `sev_max`, `blood_size` and `blood_root` since 0029 with nothing defending their direction, so a rewrite could lower a clause's inherited severity to zero and every column in the insert would still be individually legal — which is precisely the laundering path the product exists to close, because `virulence` is banded from ancestral severity and the clearance lattice keys on `virulence`, so a version that has shrunk its ancestry to routine has bought itself the whole disposition vocabulary including the constructors that dismiss the control outright. It cannot be a CHECK: §4.1 law 1 forbids a CHECK expression from seeing another row and the parent version is another row, so it is a trigger function, and the SQLSTATE is P0001 because that is what spec/conformance/manifest.toml CF-56 pins against this exact function name.
--
-- migration:  0141_fn_clause_version_guard
-- domain:     datamodel
-- band:       0140-0144 · datamodel/dm-functions-triggers + algorithms · AUTHORED, allocated by
--             verticals/mainline/db/migrations.allocation.toml (MR-6 lock 1), "vertical PL/pgSQL
--             functions". 0140 is taken by algorithms' fn_delta_witness_guard; this file takes
--             the next number in the same band and the trigger takes 0146 in the trigger band,
--             preserving the +5 pairing 0140/0145 established.
-- statements: 1  (the CREATE FUNCTION, and nothing else — the trigger is 0146)
-- invariants: I05  — ancestry monotone (spec/invariants/I05-ancestry-monotone.md). Its MECHANISM
--                    table names THIS function, `fn_clause_version_guard()`, as the
--                    version-level guard, and its OBSERVABLE table pins the SQLSTATE at P0001.
--             MI15 — blame ancestry never shrinks. `sev_max` and `blood_size` are monotone along
--                    the version chain (ARCHITECTURE.md §16, migration 0029 section 4).
-- conformance: CF-56 · expect_sqlstate P0001 · expect_constraint `mainline.fn_clause_version_guard`
--             · profile mainline · refusal_depth_min 1 · milestone K3. The function name is not a
--             preference; it is the exhibit the manifest already names.
-- source:     ARCHITECTURE.md §5.3 (the four BLOODLINE columns) · §16 MI15 · §4.1 law 1
--             · spec/invariants/I05-ancestry-monotone.md · migration 0029 sections 4 and 5
--             · docs/leads/datamodel.md §0 (a column a gate reads is enforced, never trusted)
-- requires:   0029 mainline.clause_version (the table, its BLOODLINE columns, and
--             fk_parent_version — the composite self-FK this guard's correctness rests on)
-- attached by: 0146_trg_clause_version_guard.sql. This function refuses nothing until that
--             statement exists, and that statement cannot exist until this one does.
-- sqlstate:   P0001, six times, six distinct messages. Nothing else. No path returns a value
--             that alters the row: this is an AFTER trigger and its return value is discarded.
-- forward-only; no .down.sql exists at or below the protected floor (DM-14).
--
-- ═════════════════════════════════════════════════════════════════════════════════════════════
-- WHAT THIS REFUSES, AND WHY EACH ONE IS A SEPARATE MESSAGE
-- ═════════════════════════════════════════════════════════════════════════════════════════════
-- A refusal that tells the writer the wrong thing costs an hour, so the six are not folded into
-- one. Every message begins `MAINLINE: ` and is pinned verbatim by
-- tests/integration/schema/test_mi_clause_version_bloodline.py.
--
--   R1  INSERT · `sev_max` below the parent's
--         MAINLINE: blame ancestry never shrinks — this version lowers sev_max below its parent
--       THE INVARIANT ITSELF. A rewrite may reword an obligation, retitle it, renumber it and
--       move it to another document; it may not reduce the recorded severity of what wrote it.
--
--   R2  INSERT · `blood_size` below the parent's
--         MAINLINE: blame ancestry never shrinks — this version lowers blood_size below its parent
--       The mass half. `sev_max` is a maximum, so dropping every ancestor except the worst one
--       leaves `sev_max` untouched while nine years of accumulated obligation quietly disappears.
--       Guarding the maximum without guarding the count guards nothing.
--
--   R3  INSERT · `blood_root` changed while `blood_size` did not
--         MAINLINE: blood_root changed while blood_size did not — an MMR over an unchanged multiset has an unchanged root
--       `blood_root` is a Merkle Mountain Range root over {H(event_id || severity)} of the whole
--       ancestry and `blood_size` is how many facts are in it. If the child accumulated nothing
--       new, its multiset IS its parent's, so its root must be byte-identical. A changed root at
--       an unchanged size is a re-rooting: someone replaced the commitment while keeping the
--       count, which is how you make a bounded disclosure proof point at a different history.
--       This is the refusal that stops `blood_root` from being decorative.
--
--   R4  INSERT · `parent_version` = `commit_id`
--         MAINLINE: a clause version may not declare itself its own parent
--       Not paranoia — MEASURED. `fk_parent_version` is satisfied at end of statement, by which
--       time the row itself exists, so a self-parented version passes referential integrity and
--       then compares its ancestry against ITSELF and trivially passes this guard. Without this
--       branch the guard has a one-column bypass. On the tree as it stands today, before this
--       file, such a row is ACCEPTED; that is recorded in the evidence table below.
--
--   R5  INSERT · the parent row is not readable
--         MAINLINE: the parent clause version is not readable — MI15 cannot be decided, so the write is refused
--       P2 fail-closed: a guard that cannot read its authoritative source refuses rather than
--       waves through. UNREACHABLE while `fk_parent_version` exists — measured; see EVIDENCE S8
--       and S9, where the FK refuses first with 23503 and this branch never runs. It is here for
--       the day somebody drops the FK, and it is honestly labelled as unreachable rather than
--       counted as a live refusal.
--
--   R6  UPDATE · `sev_max` lowered, `blood_size` lowered, or the root swapped at unchanged size
--         MAINLINE: blame ancestry never shrinks — this update lowers clause_version.sev_max
--         MAINLINE: blame ancestry never shrinks — this update lowers clause_version.blood_size
--         MAINLINE: blood_root changed while blood_size did not — an MMR over an unchanged multiset has an unchanged root
--       The same invariant against the same row rather than against a parent. `clause_version` is
--       append-only BY INTENT and nothing on the tree enforces that yet, so an UPDATE is today
--       the SHORTEST path to a shrunken ancestry — shorter than writing a child at all. Covering
--       INSERT and leaving UPDATE open would be guarding the front door of an open building. The
--       UPDATE arm needs no parent lookup: it compares OLD with NEW on one row, so it is exact,
--       order-independent, and free. Raising `sev_max`, growing `blood_size`, or re-rooting
--       ALONGSIDE a size increase are all admitted — a projector that learns of a new blame edge
--       must be able to write it, and MI15 is monotone, not immutable.
--
-- ═════════════════════════════════════════════════════════════════════════════════════════════
-- WHY THIS IS AN `AFTER` TRIGGER, WHEN 0029 AND THE SPEC BOTH SAY `BEFORE INSERT`
-- ═════════════════════════════════════════════════════════════════════════════════════════════
-- This is a deliberate, recorded deviation. 0029's header, test_mi_spine.py's two MI15 docstrings
-- and docs/leads/datamodel.md all describe the guard as `BEFORE INSERT`. It is attached AFTER
-- (0146), and the reason is not preference: BEFORE was BUILT and MEASURED against a live
-- CockroachDB v26.2.5, and it fails in two ways that AFTER does not.
--
-- (1) BEFORE CANNOT SEE A PARENT WRITTEN BY ITS OWN STATEMENT — a real bypass.
--     A row-level BEFORE trigger reads the statement's snapshot, so in
--         INSERT INTO mainline.clause_version VALUES (parent…), (shrinking child…);
--     the child's BEFORE trigger cannot see the parent. It has two options and both are wrong:
--     return NEW (the parent looks absent, the FK is satisfied at end of statement by the row the
--     same statement just wrote, and the shrink COMMITS — a one-statement bypass of MI15), or
--     RAISE (and then every legitimate multi-row load of a version chain is refused, which is
--     exactly what a corpus loader does). Both were executed. See EVIDENCE S15/S16.
--
-- (2) BEFORE STEALS 23503 FROM `fk_parent_version` — it breaks a green test.
--     BEFORE triggers run ahead of referential integrity, so a dangling or cross-clause
--     `parent_version` reaches R5 and is refused P0001 instead of 23503. Measured. That would
--     turn test_mi_spine.py::test_a_version_may_not_take_its_parent_from_another_clause — a
--     currently GREEN test asserting 23503 on fk_parent_version by name — red, and it would do it
--     by replacing a referential-integrity exhibit with a trigger message, which is a worse
--     courtroom exhibit for the same fact.
--
-- AFTER has neither defect and loses nothing. An AFTER ROW trigger sees every row its statement
-- wrote, so the multi-row chain is checked; the FK is evaluated first, so 23503 survives with its
-- constraint name intact; and the refusal is still a refusal — the statement and its transaction
-- abort, no other reader observes the row, and under SERIALIZABLE there is no window in which the
-- shrunken version is visible. The one property BEFORE has and AFTER does not is that the row is
-- never physically written; MI22's guard (0145) needs that property and is correctly BEFORE. MI15
-- does not: nothing here projects a column onto the row, so there is nothing for a later trigger
-- to read in between.
--
-- ── EVIDENCE — executed 2026-08-09 against CockroachDB CCL v26.2.5 (container `mainline-crdb`) ─
-- Method: a fresh database, migrations 0001-0049a applied through the tree in lexicographic
-- order (105-file tree, 0001-0049 subset, 0 failures), then this function and 0146 applied, then
-- one statement per scenario with the SQLSTATE and message captured. "RED" is the same matrix run
-- against the same schema with no guard installed at all.
--
--   #    scenario                                          RED (no guard)   BEFORE       AFTER (shipped)
--   S1   birth version, parent NULL                        accepted         accepted     accepted
--   S2   child lowers sev_max 5 -> 0                       ACCEPTED         P0001 R1     P0001 R1
--   S3   child restates: same sev/size, same root          accepted         accepted     accepted
--   S4   child grows blood_size 7 -> 9, new root           accepted         accepted     accepted
--   S5   child lowers blood_size 9 -> 3                    ACCEPTED         P0001 R2     P0001 R2
--   S6   child re-roots at unchanged blood_size            ACCEPTED         P0001 R3     P0001 R3
--   S7   self-parent                                       ACCEPTED         P0001 R4     P0001 R4
--   S8   dangling parent pointer                           23503 fk         P0001 R5 ✗   23503 fk ✓
--   S9   parent belongs to another clause                  23503 fk         P0001 R5 ✗   23503 fk ✓
--   S10  UPDATE lowers sev_max 5 -> 1                      ACCEPTED         P0001 R6     P0001 R6
--   S11  UPDATE sets sev_max to its own value              accepted         accepted     accepted
--   S12  UPDATE lowers blood_size 9 -> 2                   ACCEPTED         P0001 R6     P0001 R6
--   S13  UPDATE re-roots at unchanged blood_size           ACCEPTED         P0001 R6     P0001 R6
--   S14  UPDATE grows blood_size 9 -> 12 with a new root   accepted         accepted     accepted
--   S15  ONE statement: parent + shrinking child           ACCEPTED         (see below)  P0001 R1 ✓
--   S16  ONE statement: parent + growing child             accepted         P0001 R5 ✗   accepted ✓
--
-- S15 under BEFORE is the whole argument. With the fail-closed R5 branch, BEFORE refuses S15 —
-- but it refuses S16 identically, so it is not enforcing MI15, it is refusing multi-row inserts.
-- With R5 relaxed to `RETURN NEW`, the same shape was executed on a reduced table and the
-- shrinking child was ACCEPTED (`INSERT 0 2`). There is no configuration of a BEFORE trigger that
-- gets S8, S9, S15 and S16 all right. AFTER gets all four.
--
-- ── PLATFORM NOTES, ALL VERIFIED ON v26.2.5 RATHER THAN ASSUMED ───────────────────────────────
-- (a) OLD/NEW must be PARENTHESISED when a column is read — `(NEW).sev_max`, not `NEW.sev_max`.
--     A documented CockroachDB limitation; the same correction 0140 carries.
-- (b) `TG_OP` is populated and comparable to a string literal in a v26.2.5 trigger function, and
--     `OLD` is populated in the UPDATE arm. Both were exercised, not assumed: S10-S14 are the
--     UPDATE arm, and they only run if `TG_OP = 'UPDATE'` evaluated true.
-- (c) `AFTER INSERT OR UPDATE` — one trigger, two events — is accepted, and
--     information_schema.triggers reports it as two rows sharing the name `clause_version_guard`.
-- (d) A multi-target `SELECT … INTO a, b, c` inside a trigger function is accepted.
-- (e) `RETURN NULL` from an AFTER trigger is accepted and discards nothing that matters: an AFTER
--     trigger's return value is ignored, which is why no arm here returns `NEW`.
-- (f) Coexistence: `clause_version_guard` (AFTER) and algorithms' `z_delta_witness_required`
--     (BEFORE, 0145) sit on `mainline.clause_version` together and neither disturbs the other.
--     No claim is made here about the firing ORDER of two row-level triggers — this function, like
--     0140's, reads only columns the write itself supplies plus one authoritative row of its own
--     table, so its answer does not depend on that order.
--
-- ── WHAT THIS DOES NOT CLAIM ─────────────────────────────────────────────────────────────────
-- * It does not claim the ancestry is COMPLETE. A blame edge nobody derived is not in the count,
--   and monotonicity says nothing about edges never found. It forecloses shrinkage, not omission.
-- * It does not claim `blood_root` is a correct MMR root. It checks one exact consequence of MMR
--   semantics — an unchanged multiset has an unchanged root — and nothing else. Verifying that a
--   root actually commits to the peaks is the custody layer's arithmetic, not a trigger's.
-- * It does not close the BIRTH DODGE. A writer can declare `parent_version IS NULL` and start a
--   fresh lineage at zero. That is by design: 0029 makes the NULL a VISIBLE CLAIM ("this is a
--   birth version") that the matcher and the Conservation of Blame Mass ledger in 0049
--   interrogate, and an orphaned obligation surfaces there as a louder gate than the one it was
--   hiding from. This file closes one hole and names the other; it does not claim both.
-- * REFUSAL DEPTH IS 1, and CF-56 asks for 1. Structurally there is a second, weaker layer —
--   0029's `sev_range` CHECK still refuses a severity outside 0-5 for every writer with every
--   trigger disabled — but that is a different statement and is not counted here.
--   `ALTER TABLE mainline.clause_version DISABLE TRIGGER clause_version_guard` succeeds; the
--   custodian patrol surfaces it as an attested ledger leaf. Admin can remove the guard; admin
--   cannot remove the record that they removed it.

CREATE FUNCTION mainline.fn_clause_version_guard() RETURNS TRIGGER LANGUAGE PLpgSQL AS $$
DECLARE
  p_sev_max    INT2;
  p_blood_size INT8;
  p_blood_root BYTES;
BEGIN
  -- ── R6 · the UPDATE arm: one row against its own former self. No parent lookup, so no
  --        dependence on statement snapshots or on any other trigger.
  IF TG_OP = 'UPDATE' THEN
    IF (NEW).sev_max < (OLD).sev_max THEN
      RAISE EXCEPTION USING ERRCODE = 'P0001',
        MESSAGE = 'MAINLINE: blame ancestry never shrinks — this update lowers clause_version.sev_max';
    END IF;

    IF (NEW).blood_size < (OLD).blood_size THEN
      RAISE EXCEPTION USING ERRCODE = 'P0001',
        MESSAGE = 'MAINLINE: blame ancestry never shrinks — this update lowers clause_version.blood_size';
    END IF;

    IF (NEW).blood_size = (OLD).blood_size AND (NEW).blood_root <> (OLD).blood_root THEN
      RAISE EXCEPTION USING ERRCODE = 'P0001',
        MESSAGE = 'MAINLINE: blood_root changed while blood_size did not — an MMR over an unchanged multiset has an unchanged root';
    END IF;

    RETURN NULL;
  END IF;

  -- ── the INSERT arm. A birth version declares no parent and has no ancestry to shrink; 0029's
  --    MATCH SIMPLE composite FK makes that declaration first-class rather than a special case.
  IF (NEW).parent_version IS NULL THEN
    RETURN NULL;
  END IF;

  -- ── R4 · a self-parented row satisfies fk_parent_version (the row exists by the time the FK is
  --        evaluated) and would then compare its ancestry against itself. Refuse before looking.
  IF (NEW).parent_version = (NEW).commit_id THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = 'MAINLINE: a clause version may not declare itself its own parent';
  END IF;

  -- ── the authoritative row. One seek: (clause_uuid, commit_id) is cv_clause_commit_unique, and
  --    clause_uuid appears on both sides of fk_parent_version, so lineage cannot cross clauses.
  SELECT cv.sev_max, cv.blood_size, cv.blood_root
    INTO p_sev_max, p_blood_size, p_blood_root
    FROM mainline.clause_version cv
   WHERE cv.clause_uuid = (NEW).clause_uuid
     AND cv.commit_id   = (NEW).parent_version;

  -- ── R5 · fail closed. `sev_max` is NOT NULL, so a NULL here means no row. Unreachable while
  --        fk_parent_version stands (measured: the FK refuses first, 23503); present for the day
  --        it does not.
  IF p_sev_max IS NULL THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = 'MAINLINE: the parent clause version is not readable — MI15 cannot be decided, so the write is refused';
  END IF;

  -- ── R1 · the O-Ring Ratchet.
  IF (NEW).sev_max < p_sev_max THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = 'MAINLINE: blame ancestry never shrinks — this version lowers sev_max below its parent';
  END IF;

  -- ── R2 · the mass half. A maximum survives the deletion of every ancestor but one.
  IF (NEW).blood_size < p_blood_size THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = 'MAINLINE: blame ancestry never shrinks — this version lowers blood_size below its parent';
  END IF;

  -- ── R3 · no silent re-rooting. Same multiset, same MMR root; a new root at an unchanged size
  --        is a swapped commitment.
  IF (NEW).blood_size = p_blood_size AND (NEW).blood_root <> p_blood_root THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = 'MAINLINE: blood_root changed while blood_size did not — an MMR over an unchanged multiset has an unchanged root';
  END IF;

  RETURN NULL;
END $$;
