-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- MI: MI01
-- I: I06
-- COUNSEL-GATED: no
-- RATIONALE: I06 says a dependency edge a gate consumes is COMPUTED, never declared — and the difference between a computed edge and a declared one is invisible after the fact unless the row is made to prove it. This table refuses an edge that cannot name the overlap it claims (23514 on overlap_nonempty), refuses the reverse row and the self-edge (23514 on canonical_direction), and refuses an anonymous deriver (23514 on computed_by_stated). What is left is a dependency assertion that carries its own derivation, which is the only kind a gate may read.
--
-- migration:  0049b_commutation_edge
-- domain:     algorithms
-- worker:     origin-diff (W6) — COMMUTATION FOOTPRINT
-- band:       0049a-0049z · algorithms · AUTHORED, allocated by
--             verticals/mainline/db/migrations.allocation.toml (MR-6 lock 1), which grants the
--             letter space of 0049 to the algorithms domain EXPLICITLY AND EXCLUSIVELY as the
--             algorithms table annexe. 0049a is `delta_witness` (worker W4); this is the second
--             file in that annexe and it takes the next letter.
-- statements: 1
-- invariants: I06  — a dependency edge consumed by a gate is computed, never declared
--                    (ARCHITECTURE.md §3.2, mechanism M1).
--             MI01 — evidentiary tables are append-only. SEE THE HONEST LIMIT BELOW: the
--                    BEFORE UPDATE/DELETE trigger that enforces MI01 for this table is OWED and
--                    is NOT in this file, because one file carries one statement and the trigger
--                    band is 0145-0149.
-- source:     ARCHITECTURE.md §3.2 I06 · §3.3 M1 (COMMUTATION BLAME) · §5.2 (commit_obj) ·
--             §5.3 (clause_version, cv_clause_commit_unique)
--             docs/leads/algorithms.md §2 COMMUTATION FOOTPRINT (written as 0206; RELOCATED to
--             the 0049a-0049z annexe by the migration reconciliation ruling of 2026-08-08 — the
--             0200-0219 annexe is revoked and lint rule B refuses any file that claims it)
--             research/05-architecture/clause-identity.md §5
-- requires:   0001a schema mainline · 0024 mainline.commit_obj · 0028 mainline.clause ·
--             0029 mainline.clause_version (for cv_clause_commit_unique, which both composite
--             foreign keys point at)
-- computed:   every row is derived by mainline_domain.diachronic.commutation.
--             derive_commutation_edges and carries `computed_by` and `footprint_ver` naming the
--             code and the encoding that derived it. NOTHING in this table is declared.
-- sqlstate:   23503 on fk_from_version / fk_to_version; 23505 on commutation_edge_pk;
--             23514 on canonical_direction / overlap_nonempty / computed_by_stated /
--             footprint_ver_stated / from_commit_is_sha256 / to_commit_is_sha256
-- forward-only; no .down.sql exists at or below the protected floor (DM-14).
--
-- ═════════════════════════════════════════════════════════════════════════════════════════════
-- WHAT A ROW MEANS, IN ONE SENTENCE
-- ═════════════════════════════════════════════════════════════════════════════════════════════
-- Two clause edits DO NOT COMMUTE: their footprints — (identity anchors) ∪ (CAT parameter keys)
-- ∪ (implied control class) — share at least one token, so neither edit can be read as
-- independent of the other, and `footprint_overlap` is exactly the tokens they share.
--
-- Commuting pairs are NOT stored. A table of "these two are independent" would be quadratic in
-- the corpus and would say nothing a gate reads; the interesting relation is the sparse one.
--
-- ── WHERE THE IDEA COMES FROM, AND WHERE IT DOES NOT ─────────────────────────────────────────
-- Patch commutation is Darcs' and Pijul's, published and well studied: two patches commute when
-- they touch disjoint regions, and a version-control system that knows which patches commute can
-- reorder, cherry-pick and merge without a three-way diff. That machinery is theirs and none of
-- it is claimed here.
--
-- What is transplanted is the SUBJECT. The "region" a safety-control edit touches is not a line
-- range — line ranges churn on every retypeset and would make every pair of edits to one document
-- non-commuting — it is the set of things the clause is ABOUT: which equipment, which controlled
-- parameter, which class of control. Two edits about the same pump are dependent whether or not
-- they touched the same paragraph, and two edits to adjacent paragraphs about different equipment
-- are not. `novelty/commutation-footprint.yaml` labels this a TRANSPLANT and names the prior art.
--
-- ═════════════════════════════════════════════════════════════════════════════════════════════
-- THE THREE CHECKS, AND WHY EACH IS A CHECK RATHER THAN A CONVENTION
-- ═════════════════════════════════════════════════════════════════════════════════════════════
--
-- `overlap_nonempty` — A DEPENDENCY THAT CANNOT NAME ITS OVERLAP IS A DECLARATION.
--   This is the I06 constraint and it is the reason this table is more than a cache. A row here
--   asserts that a gate should widen its antecedent set; the evidence for that assertion is the
--   shared tokens; a row with an empty array asserts the conclusion and withholds the evidence.
--   Refused, 23514, for every writer including one that never imported this repository's code.
--
--   PLATFORM TRAP, MEASURED AND WORKED AROUND IN THE OBVIOUS PLACE: `array_length(x, 1)` returns
--   NULL — not 0 — for an empty array, and a CHECK whose expression evaluates to NULL PASSES.
--   Written the naive way this constraint would admit precisely the rows it exists to refuse.
--   Hence the COALESCE, which is not defensive style: it is the constraint.
--
-- `canonical_direction` — SYMMETRY AND IRREFLEXIVITY, ENFORCED RATHER THAN OBSERVED.
--   Commutation is a symmetric, irreflexive relation. Stored naively that means two rows per
--   pair, which can disagree after a partial re-derivation, plus the possibility of a self-edge,
--   which is never a derivation and always a bug. A strict lexicographic ordering on
--   (commit_id, clause_uuid) makes the reverse row and the self row UNSTORABLE. The Python
--   canonicaliser (mainline_domain.diachronic.commutation.canonical) produces exactly the rows
--   this expression accepts, and a Hypothesis property in
--   tests/unit/domain/diachronic/test_commutation.py holds the two equal over every ordering of
--   a small pool, including the equal-commit case.
--
--   That agreement rests on a fact worth stating: CockroachDB compares BYTES lexicographically
--   and UUID by its 128-bit value, which is the order Python's `bytes` and `uuid.UUID` give.
--   The property test asserts it rather than trusting it.
--
--   Written out longhand instead of as a row-value comparison `(a, b) < (c, d)`. The tuple form
--   is standard SQL and CockroachDB implements it, but a CHECK is the wrong place to depend on a
--   parse the whole table's storability turns on, and the longhand form is what a reader
--   verifying the Python canonicaliser against this file has to read anyway.
--
-- `computed_by_stated` / `footprint_ver_stated` — AN ANONYMOUS DERIVATION IS A DECLARATION.
--   After the fact, the only thing separating a row somebody COMPUTED from a row somebody TYPED
--   is that the computed one names the code and the encoding that produced it. `footprint_ver`
--   matters as much as `computed_by`: changing what counts as "touched" changes which edits
--   commute, which changes what a gate reads, so it is a version and a re-derivation — not a
--   refactor, and never an in-place update of rows a gate has already read.
--
-- ═════════════════════════════════════════════════════════════════════════════════════════════
-- WHY BOTH FOREIGN KEYS ARE COMPOSITE, AND WHY THAT IS FREE HERE
-- ═════════════════════════════════════════════════════════════════════════════════════════════
-- (clause_uuid, commit_id) -> mainline.clause_version's `cv_clause_commit_unique`. A derived edge
-- names two VERSIONS, not two clauses, and a pointer that resolves to a clause but not to the
-- version of it that was edited is a pointer to the wrong fact.
--
-- 0049a could not take this constraint: `delta_witness` rows must be written BEFORE the
-- clause_version row they explain, CockroachDB checks foreign keys per statement and does not
-- implement DEFERRABLE, so the FK and the ordering contract were directly incompatible. That
-- problem does not exist here. Commutation edges are DERIVED — after both versions are committed,
-- off the gate path, by the projector — so both parents always already exist. The constraint that
-- was unbuildable one file earlier is free in this one, and taking it is not inconsistent with
-- that decision, it is the same reasoning reaching a different answer on different facts.
--
-- ── NO CASCADE, ANYWHERE ─────────────────────────────────────────────────────────────────────
-- Neither FK carries ON DELETE or ON UPDATE. `clause_version` is append-only, so nothing upstream
-- moves; and a CASCADE on a table of derived safety dependencies would let a delete somewhere
-- else silently retract an antecedent a gate had already read.
--
-- ═════════════════════════════════════════════════════════════════════════════════════════════
-- HONEST LIMITS, STATED WHERE SOMEBODY WILL READ THEM
-- ═════════════════════════════════════════════════════════════════════════════════════════════
--
-- (1) APPEND-ONLY IS NOT YET ENFORCED, AND THIS FILE SAYS SO.
--     MI01 wants a BEFORE UPDATE/DELETE trigger calling `mainline.fn_refuse_mutation` (migration
--     0107), attached the way 0128a-0128j attach it to ten other tables. It is NOT in this file:
--     MR-5 permits exactly one top-level statement per file and a trigger belongs in the vertical
--     trigger band (0145-0149), which this domain shares with datamodel/dm-functions-triggers.
--     Until that trigger is attached, this table is append-only by GRANT and by convention only —
--     an owner-level UPDATE succeeds. The same disclosure discipline 0029 applies to MI15 applies
--     here: an unenforced invariant is written down as unenforced, because a suite that has never
--     been red asserts nothing (PL-2) and a header that overclaims is worse than one that does
--     not mention the invariant at all.
--
-- (2) SITE_ID IS NOT IN THE PRIMARY KEY AND CARRIES NO FOREIGN KEY.
--     It is out of the key because a commit is already site-scoped through mainline.commit_obj,
--     and putting the site in the key would let two rows for one pair exist under two site
--     values — which is a disagreement the CHECKs above could not see. It carries no FK for the
--     same reason mainline.clause_version's does not: the spine denormalises `site_id` for RLS
--     scoping and index prefixes, and the authoritative binding is through the commit. An RLS
--     policy over this table belongs in the policy band (0180-0198) and is owed to whoever needs
--     it; until then access is by GRANT, and that is stated rather than implied.
--
-- (3) THIS TABLE REFUSES NOTHING A MERGE CARES ABOUT, AND IT IS NOT MEANT TO.
--     It widens the antecedent set the existing weaken gate reads. The refusal is the kernel's
--     (MI02 / MI30) and is unchanged. What this file contributes is that the antecedents are
--     derived from the documents rather than declared by the author of the change — which is the
--     whole of I06 and none of the gate.
--
-- (4) THE FOOTPRINT IS WIDE AND THE NUISANCE COST IS UNMEASURED.
--     A footprint is the union over both versions ("in scope of"), not the symmetric difference
--     ("changed by"), so edits commute less often than a narrow reading would give and more
--     dependency edges exist. That is the fail-closed direction — a wider antecedent set can only
--     make a gate louder — but how much louder is a measurement nobody has taken. Worker W10's
--     mutation ratchet is what takes it, and `novelty/commutation-footprint.yaml` carries the
--     admission under `unverified` rather than in the claim.

CREATE TABLE mainline.commutation_edge (
  site_id           UUID        NOT NULL,
  from_commit       BYTES       NOT NULL,
  from_clause_uuid  UUID        NOT NULL,
  to_commit         BYTES       NOT NULL,
  to_clause_uuid    UUID        NOT NULL,
  footprint_overlap STRING[]    NOT NULL,   -- the shared tokens. Sorted, and never empty.
  computed_by       STRING      NOT NULL,   -- agent identity + version of the deriver
  footprint_ver     STRING      NOT NULL,   -- WHICH encoding decided what "touched" means
  computed_at       TIMESTAMPTZ NOT NULL DEFAULT now(),

  CONSTRAINT commutation_edge_pk PRIMARY KEY
    (from_commit, from_clause_uuid, to_commit, to_clause_uuid),
  CONSTRAINT fk_from_version FOREIGN KEY (from_clause_uuid, from_commit)
    REFERENCES mainline.clause_version (clause_uuid, commit_id),
  CONSTRAINT fk_to_version FOREIGN KEY (to_clause_uuid, to_commit)
    REFERENCES mainline.clause_version (clause_uuid, commit_id),
  -- Symmetry and irreflexivity, made unstorable rather than merely undesirable.
  CONSTRAINT canonical_direction CHECK (
    from_commit < to_commit
    OR (from_commit = to_commit AND from_clause_uuid < to_clause_uuid)
  ),
  -- I06: a dependency that cannot name its overlap is a declaration. COALESCE because
  -- array_length() answers NULL for an empty array and a NULL CHECK expression PASSES.
  CONSTRAINT overlap_nonempty CHECK (COALESCE(array_length(footprint_overlap, 1), 0) >= 1),
  CONSTRAINT computed_by_stated CHECK (computed_by <> ''),
  CONSTRAINT footprint_ver_stated CHECK (footprint_ver <> ''),
  CONSTRAINT from_commit_is_sha256 CHECK (length(from_commit) = 32),
  CONSTRAINT to_commit_is_sha256 CHECK (length(to_commit) = 32),
  -- Rows are stored in one canonical direction, so "what does this edit depend on" is two
  -- lookups: the primary index answers the from-side, this index answers the to-side.
  INDEX by_to (to_commit, to_clause_uuid),
  INDEX by_site_commit (site_id, from_commit) STORING (footprint_ver)
);
