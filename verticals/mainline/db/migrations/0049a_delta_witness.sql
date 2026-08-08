-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- MI: MI22
-- I: I14
-- COUNSEL-GATED: no
-- RATIONALE: I14 says a refusal that cannot state its irreducible reason set gets routed around, and an invariant that is routed around is not an invariant. This table is what turns "the gate explains itself" from a rendering concern into a WRITE PRECONDITION: a lattice weakening with no row here cannot be stored at all, because 0140/0145 refuse the clause_version that claims it.
--
-- migration:  0049a_delta_witness
-- domain:     algorithms
-- band:       0049a-0049z · algorithms · AUTHORED, allocated by
--             verticals/mainline/db/migrations.allocation.toml (MR-6 lock 1), which grants the
--             letter space of 0049 to the algorithms domain EXPLICITLY AND EXCLUSIVELY as the
--             algorithms table annexe. This is a declared band, not a borrowed one — band
--             borrowing failed in the incident of 2026-08-08 because it was undeclared, not
--             because it happened (MRR-5).
-- statements: 1
-- invariants: I14  — every refusal emits an irreducible reason set and, where computable,
--                    the nearest admissible alternative (ARCHITECTURE.md §3.1).
--             MI22 — the gate fails closed on a stale or absent projection: a `weaken` whose
--                    explanation is absent is refused rather than stored unexplained.
-- source:     ARCHITECTURE.md §3.1 (minimal unsatisfiable subset) · §5.3 (clause_version)
--             docs/leads/algorithms.md D8, §9 (written as 0205; RELOCATED to 0049a by
--             docs/leads/migration-reconciliation.md §5.4 and MR-7)
--             research/05-architecture/clause-identity.md §6.2 (the nine rules)
-- requires:   0001a schema mainline · 0024 mainline.commit_obj · 0028 mainline.clause
-- sqlstate:   23503 on fk_clause / fk_commit; 23505 on delta_witness_pk;
--             23514 on rule_id_closed / witness_ord_nonneg / field_stated / note_stated /
--             commit_id_is_sha256.
--             The P0001 that makes this table load-bearing lives in 0140 (the function) and is
--             attached to `mainline.clause_version` by 0145 (the trigger).
-- forward-only; no .down.sql exists at or below the protected floor (DM-14).
--
-- ═════════════════════════════════════════════════════════════════════════════════════════════
-- WHY THIS FILE IS 0049a AND NOT 0205
-- ═════════════════════════════════════════════════════════════════════════════════════════════
-- The algorithms lead allocated itself the band 0200-0219. ARCHITECTURE.md §18 ends at 0171 and
-- defines nothing at 0200; datamodel.md separately claimed 0200-0279 for views and RLS. Both
-- claims are revoked (MR-7), 0200+ is UNALLOCATED, and `trappoint migrate lint` rule B refuses
-- any file that claims a number no band grants.
--
-- The relocation is not merely a renumbering to a legal address. This file is a CREATE TABLE,
-- and a CREATE TABLE belongs in the TABLE SPACE — before the function, trigger, view and policy
-- strata, not after them. At 0205 this table was created after every trigger that reads it,
-- which is an inverted stratification that happened to work only because nothing in 0100-0199
-- was applied against real rows during the migration run. Its dependencies (0024 `commit_obj`,
-- 0028 `clause`, and 0029 `clause_version` for the ordering contract below) are all far
-- earlier, and its only reader is the guard at 0140/0145, which is far later. 0049a sits
-- exactly where both facts are satisfied and where the allocation grants it a number.
--
-- Nothing below this line changed in the relocation except cross-references to the numbers that
-- moved: the SQL body is byte-for-byte what was verified at 0205.
--
-- ═════════════════════════════════════════════════════════════════════════════════════════════
-- WHAT THIS TABLE IS FOR, IN ONE SENTENCE
-- ═════════════════════════════════════════════════════════════════════════════════════════════
-- Decision D8: a `clause_version` declaring `control_delta IN ('weaken','remove')` with
-- `delta_basis = 'lattice'` and NO row here for its own (clause_uuid, commit_id) is REFUSED by
-- `mainline.fn_delta_witness_guard` (migration 0140, attached by 0145, P0001). An unexplainable
-- weakening verdict does not get to exist in this database — not "is flagged", not "is logged":
-- cannot be stored.
--
-- Invariant I14 says a gate that only says "no" gets routed around, and an invariant that is
-- routed around is not an invariant. That turns the refusal message from a rendering concern
-- into a WRITE PRECONDITION, which is the only place it cannot be quietly dropped.
--
-- ── THE TWO SETS, AND WHY `minimal` IS A COLUMN ──────────────────────────────────────────────
--
-- I14 asks for two different things and they are not the same subset:
--
--   the MINIMAL UNSATISFIABLE SUBSET   why the answer is no. Removing any member changes the
--                                      verdict. `minimal = true`.
--   the MINIMAL CORRECTION SET         the nearest admissible alternative — what would have to
--                                      change for the answer to be yes. Every row here,
--                                      minimal or not, when the verdict is a refusal.
--
-- Because the lattice's verdict is a JOIN over nine independent rules, the minimal
-- unsatisfiable subset is a singleton for every rule combination the lattice can currently
-- produce: one rule attains the maximum on its own. The correction set is usually larger —
-- when four rules each independently weaken, citing one of them is the irreducible reason and
-- undoing one of them fixes nothing. Storing only the singleton would make the refusal
-- truthful and useless. Storing everything with no `minimal` flag would make it a dump.
-- Both, flagged, is what I14 actually asks for.
--
-- `minimal` carries `DEFAULT true` so a writer that names only the eight columns the interface
-- specifies still produces a legal row, and the default is the conservative one: a row nobody
-- classified is treated as part of the reason set rather than as decoration.
--
-- ═════════════════════════════════════════════════════════════════════════════════════════════
-- THE ORDERING CONTRACT — NORMATIVE. READ BEFORE WRITING A PROJECTOR.
-- ═════════════════════════════════════════════════════════════════════════════════════════════
--
--   BEGIN;
--     INSERT INTO mainline.delta_witness (...);   -- every witness, FIRST
--     INSERT INTO mainline.clause_version (...);  -- the version row, SECOND
--   COMMIT;
--
-- The guard — function 0140, trigger 0145 — is a BEFORE INSERT trigger on
-- `mainline.clause_version`, so it can only see rows that are already in the transaction when
-- the version row arrives. Witnesses written afterwards are witnesses the guard never saw, and
-- a version row that got past the guard because its explanation had not been written yet is
-- exactly the row D8 exists to prevent.
--
-- The two statements MUST be in one transaction. Witnesses committed without their version row
-- are an orphaned proposal — harmless, and swept by the projector — but a version row committed
-- without its witnesses cannot happen, because the guard refuses it.
--
-- ═════════════════════════════════════════════════════════════════════════════════════════════
-- THE COMPOSITE FK THE DESIGN ASKS FOR IS UNBUILDABLE ON THIS PLATFORM. WHAT IS HERE INSTEAD.
-- ═════════════════════════════════════════════════════════════════════════════════════════════
-- The natural constraint is
--
--   FOREIGN KEY (clause_uuid, commit_id)
--     REFERENCES mainline.clause_version (clause_uuid, commit_id)   -- cv_clause_commit_unique
--
-- and it is DIRECTLY INCOMPATIBLE with the ordering contract above. CockroachDB checks foreign
-- keys per statement and does not implement `DEFERRABLE` / `INITIALLY DEFERRED`
-- (cockroachdb/cockroach#9897, #31632, open since 2016; v26.2 answers `unimplemented at or near
-- "deferred"`, and the v26.2 foreign-key reference still says RESTRICT and NO ACTION are
-- "equivalent until options for deferring constraint checking are added"). So the first
-- statement of the transaction would be refused with 23503 for pointing at a row the second
-- statement has not written yet. This is a MEASURED platform limit, not a preference, and it is
-- recorded here rather than worked around silently.
--
-- What is enforced instead, and it is not nothing:
--
--   fk_clause  (clause_uuid)  -> mainline.clause      a witness cites a clause that exists.
--                                                     `clause_version` itself FK-references
--                                                     `clause`, so the parent is always already
--                                                     there when the witnesses are written. A
--                                                     `weaken` is never a birth version, so the
--                                                     clause row predates this commit anyway.
--   fk_commit  (commit_id)    -> mainline.commit_obj  a witness cites a commit that exists.
--                                                     `clause_version.fk_commit` means the
--                                                     commit object is written before any of its
--                                                     versions, so this too is always satisfiable
--                                                     at witness-insert time.
--
-- What is NOT enforced by referential integrity is the PAIRING — that (clause_uuid, commit_id)
-- names a version row that exists. The guard at 0140/0145 enforces the direction that matters (a
-- version row with no witness for its own pair is refused); the other direction leaves an
-- orphaned witness possible, which costs a sweep and refuses nothing.
--
-- HONEST LIMIT, STATED WHERE SOMEBODY WILL READ IT: this table makes a weakening carry AN
-- explanation. It cannot make the explanation TRUE. A writer who inserts a fabricated witness
-- row and then the version row satisfies the guard. What that writer cannot do is claim a
-- `weaken` with no reasons at all, and what they cannot do EITHER is dodge the gate by
-- declaring `restate` on an edit the matcher and the CBM ledger will account for independently
-- (workers W8/W9 — their migrations are unallocated until the algorithms lead is granted a band
-- for them; the 0200-0204 numbers that sentence used to cite are revoked with the rest of the
-- annexe). D8 closes one hole, names it, and does not claim the others.
--
-- ── ON THE ABSENCE OF `site_id` ──────────────────────────────────────────────────────────────
-- Every other table in `mainline` carries `site_id` for RLS scoping. This one does not, because
-- P2 requires a column a policy reads to be PROJECTED from an authoritative row by a trigger,
-- and the authoritative row here — the `clause_version` — does not exist yet when the witness is
-- written. Projecting from `mainline.clause` instead is possible and is deliberately left to a
-- follow-on PAIR — a projection trigger in the vertical trigger band 0145-0149 and its policy in
-- the RLS band 0180-0198 — owned by whoever needs the policy, so that the projection and the
-- policy land together rather than a column arriving with no trigger behind it. Until then,
-- access to this table is by GRANT, and that is stated rather than implied.
--
-- ── `rule_id` IS A CHECK AND NOT AN ENUM ─────────────────────────────────────────────────────
-- The nine rule ids mirror `mainline_domain.contracts.RULE_IDS`, and
-- `tests/integration/algorithms/lattice/test_0049a_shape.py` holds the two equal by parsing this
-- file. A `CREATE TYPE` would be a second migration for a vocabulary that changes only when a
-- rule is added — which is a lattice version bump (`LATTICE_VERSION`), a re-derivation of the
-- affected verdicts, and a decision somebody signs. A `CHECK` puts that vocabulary in one place
-- that an `ALTER TABLE ... DROP CONSTRAINT` makes visible in the custody ledger.

CREATE TABLE mainline.delta_witness (
  clause_uuid  UUID   NOT NULL,
  commit_id    BYTES  NOT NULL,
  witness_ord  INT2   NOT NULL,   -- 0-based, in rule order R1 -> R9; stable across two runs
  rule_id      STRING NOT NULL,   -- mirrors mainline_domain.contracts.RULE_IDS
  field        STRING NOT NULL,   -- the CAT slot (or 'anchor:<class>') the rule read
  from_repr    STRING NOT NULL,   -- the reference value, as it will be printed in the refusal
  to_repr      STRING NOT NULL,   -- the descendant value, likewise
  note         STRING NOT NULL,   -- one sentence a person can act on. Never empty.
  minimal      BOOL   NOT NULL DEFAULT true,   -- in the minimal UNSATISFIABLE SUBSET (I14)

  CONSTRAINT delta_witness_pk PRIMARY KEY (clause_uuid, commit_id, witness_ord),
  CONSTRAINT fk_clause FOREIGN KEY (clause_uuid) REFERENCES mainline.clause (clause_uuid),
  CONSTRAINT fk_commit FOREIGN KEY (commit_id)   REFERENCES mainline.commit_obj (commit_id),
  CONSTRAINT rule_id_closed CHECK (rule_id IN
    ('R1_DEONTIC', 'R2_SETPOINT', 'R3_COMPARATOR', 'R4_EXCEPTION', 'R5_QUANTIFIER',
     'R6_VERIFICATION', 'R7_FREQUENCY', 'R8_ANCHOR', 'R9_COVERAGE')),
  CONSTRAINT witness_ord_nonneg CHECK (witness_ord >= 0),
  CONSTRAINT field_stated CHECK (field <> ''),
  -- A witness with an empty note is a row that satisfies the guard and explains nothing,
  -- which is the shape D8 exists to refuse, one level down.
  CONSTRAINT note_stated CHECK (note <> ''),
  CONSTRAINT commit_id_is_sha256 CHECK (length(commit_id) = 32),
  INDEX by_commit (commit_id, clause_uuid) STORING (rule_id, minimal),
  INDEX by_rule (rule_id, commit_id)
);
