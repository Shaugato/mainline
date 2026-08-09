-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- MI: MI01
-- I: I14, I17
-- COUNSEL-GATED: no
-- RATIONALE: A kill rate is a summary, and a summary is only as good as the ability to disagree with it. One row per mutant, carrying the verdict, the witness rule ids, the residue reasons and the sentence that decided the outcome, is what lets an opposing expert recount the aggregate from the evidence instead of taking it on trust.
--
-- migration:  0049z_meas_mutation_result
-- domain:     algorithms
-- band:       0049a-0049z · algorithms · AUTHORED, allocated by
--             verticals/mainline/db/migrations.allocation.toml (MR-6 lock 1)
-- statements: 1
-- invariants: MI01 — evidentiary tables are append-only (welded by 0149z)
--             I14  — a refusal states its irreducible reason set; here, so does a MEASUREMENT
--             I17  — a published measurement states its own provenance
-- source:     docs/leads/algorithms.md §2 MUTATION RATCHET, §8 R-A1 ·
--             research/05-architecture/clause-identity.md §6.4
-- requires:   0049y mainline_meas.mutation_run
-- sqlstate:   23503 on fk_run · 23514 on kind_closed / outcome_closed / outcome_matches_kind /
--             success_matches_outcome / residue_reason_closed · P0001 on UPDATE or DELETE (0149z)
-- forward-only; no .down.sql and no .up.sql (MR-5).
--
-- ═════════════════════════════════════════════════════════════════════════════════════════════
-- WHY ONE ROW PER MUTANT AND NOT ONE ROW PER CLASS
-- ═════════════════════════════════════════════════════════════════════════════════════════════
-- Because the interesting question about a kill rate of 0.96 is always "which four?", and a
-- table of class totals cannot answer it. The rows a reader wants are the SURVIVORS: the control
-- mutations that reached the gate undetected, each with the clause it was applied to, the verdict
-- the lattice returned, and the operator's own sentence describing what it changed. That is the
-- residual risk, named, and it is the thing `docs/leads/algorithms.md` §8 R-A1 promises to
-- publish rather than argue away.
--
-- ── THE OUTCOME VOCABULARY IS CLOSED AND IT IS NOT ONE VOCABULARY ────────────────────────────
-- Decision D13: KILL and SURVIVE are two different products and there is no combined "accuracy"
-- figure anywhere in this design. So the outcome enumeration is partitioned by kind, and
-- `outcome_matches_kind` refuses a KILL row labelled 'preserved' or a SURVIVE row labelled
-- 'killed'. A mis-kinded row would be scored backwards — a false positive counted as a catch —
-- and it would move an aggregate in the flattering direction, which is the class of error every
-- CHECK in this file exists to make unrepresentable.
--
--   KILL     killed | survived
--   SURVIVE  preserved | identity_changed | false_weaken | identity_changed_and_false_weaken
--
-- `success` is the single collapse point into the boolean the Wilson arithmetic consumes, and
-- `success_matches_outcome` welds it to the label so that the two can never disagree. It is a
-- stored column rather than a computed one because CockroachDB's generated columns cannot
-- reference a value the writer supplies conditionally, and a projection this table cannot
-- recompute from an authoritative row is better held by a CHECK than pretended to be projected.
--
-- ── `chain_adjacent_max_force` IS THE ORIGINDIFF MEASUREMENT ─────────────────────────────────
-- For an N-step salami this is the loudest verdict a SYNCHRONIC gate would have seen, walking
-- the chain pair by pair. Zero means every individual commit looked like a restatement. A row
-- with `chain_adjacent_max_force = 0` and `delta = 'weaken'` is decision D7 demonstrated on
-- data: twenty individually-neutral commits whose composition against the BLAME ORIGIN is a
-- weakening, refused at commit twenty by a diachronic gate and invisible to every synchronic
-- one. A salami whose adjacent steps were individually detectable proves nothing about
-- ORIGINDIFF, and this column is what distinguishes the two cases.
--
-- ── `residue_reasons` IS THE FIVE-VALUE VOCABULARY AND THERE IS NO SIXTH ─────────────────────
-- `unmatched`, `ambiguous`, `anchor_drop`, `opaque_control`, `citation_unresolved` — exactly the
-- CHECK on `mainline.identity_residue` and the boundary note in `docs/leads/algorithms.md` §4.
-- The CHECK below holds the array to that vocabulary so that a stand-in residue derivation
-- cannot quietly invent a sixth reason and have it counted.
--
-- ── WHAT THIS TABLE DELIBERATELY DOES NOT DO ─────────────────────────────────────────────────
-- It carries no foreign key to `mainline.clause` or `mainline.clause_version`. The fixtures are
-- authored revisions in a Python package, not rows in the commit DAG, and a FK to a clause that
-- does not exist would be a lie about where the measurement came from. `fixture_id` and
-- `ancestor_canon_sha256` are what tie a row to its input, and the input is committed bytes in
-- `mainline-mutation/src/mainline_mutation/data/`, digested by `catalogue_sha256` on the run row.

CREATE TABLE mainline_meas.mutation_result (
  run_id            UUID   NOT NULL,
  mutant_id         STRING NOT NULL,          -- blake2b(seed || class || fixture), 32 hex
  kind              STRING NOT NULL,          -- 'KILL' | 'SURVIVE'
  class_id          STRING NOT NULL,
  fixture_id        STRING NOT NULL,
  family            STRING NOT NULL,
  outcome           STRING NOT NULL,
  success           BOOL   NOT NULL,
  outcome_reason    STRING NOT NULL,          -- the sentence, never empty

  -- what the pipeline actually said, kept so the outcome can be recounted
  ancestor_canon_sha256   STRING NOT NULL,
  descendant_canon_sha256 STRING NOT NULL,
  ancestor_cat_key   STRING NULL,
  descendant_cat_key STRING NULL,
  ancestor_cat_confidence STRING NOT NULL,
  descendant_cat_confidence STRING NOT NULL,
  delta             STRING NOT NULL,          -- the PATH A verdict
  delta_basis       STRING NOT NULL,
  delta_force       INT2   NOT NULL,
  ratchet_delta_without_oracle STRING NOT NULL,
  witness_rule_ids  STRING[] NOT NULL DEFAULT ARRAY[]::STRING[],
  residue_reasons   STRING[] NOT NULL DEFAULT ARRAY[]::STRING[],
  identity_recovered BOOL  NOT NULL,
  match_stage       STRING NULL,              -- 'S1' | 'S2' | 'S3' | NULL
  match_score       DECIMAL(9,6) NULL,
  anchors_considered BOOL  NOT NULL,
  chain_length      INT4   NOT NULL DEFAULT 1,
  chain_adjacent_max_force INT2 NULL,         -- the ORIGINDIFF measurement; NULL for 1-step

  CONSTRAINT mutation_result_pk PRIMARY KEY (run_id, mutant_id),
  CONSTRAINT fk_run FOREIGN KEY (run_id) REFERENCES mainline_meas.mutation_run (run_id),
  CONSTRAINT kind_closed CHECK (kind IN ('KILL', 'SURVIVE')),
  CONSTRAINT outcome_closed CHECK (outcome IN (
    'killed', 'survived',
    'preserved', 'identity_changed', 'false_weaken', 'identity_changed_and_false_weaken')),
  -- Decision D13: two catalogues, two vocabularies, scored by opposite rules.
  CONSTRAINT outcome_matches_kind CHECK (
    (kind = 'KILL' AND outcome IN ('killed', 'survived'))
    OR (kind = 'SURVIVE' AND outcome IN (
      'preserved', 'identity_changed', 'false_weaken', 'identity_changed_and_false_weaken'))
  ),
  CONSTRAINT success_matches_outcome CHECK (
    success = (outcome IN ('killed', 'preserved'))
  ),
  CONSTRAINT delta_closed CHECK (
    delta IN ('introduce', 'strengthen', 'restate', 'weaken', 'remove')
  ),
  CONSTRAINT ratchet_delta_closed CHECK (
    ratchet_delta_without_oracle IN ('introduce', 'strengthen', 'restate', 'weaken', 'remove')
  ),
  CONSTRAINT delta_force_matches CHECK (
    delta_force = CASE delta WHEN 'weaken' THEN 2 WHEN 'remove' THEN 3 ELSE 0 END
  ),
  CONSTRAINT match_stage_closed CHECK (match_stage IS NULL OR match_stage IN ('S1','S2','S3','S4')),
  -- A recovered identity names the stage that recovered it; an unrecovered one names none.
  CONSTRAINT match_stage_matches_recovery CHECK (identity_recovered = (match_stage IS NOT NULL)),
  CONSTRAINT witness_rule_ids_closed CHECK (
    witness_rule_ids <@ ARRAY['R1_DEONTIC','R2_SETPOINT','R3_COMPARATOR','R4_EXCEPTION',
                              'R5_QUANTIFIER','R6_VERIFICATION','R7_FREQUENCY','R8_ANCHOR',
                              'R9_COVERAGE']
  ),
  CONSTRAINT residue_reason_closed CHECK (
    residue_reasons <@ ARRAY['unmatched','ambiguous','anchor_drop','opaque_control',
                             'citation_unresolved']
  ),
  CONSTRAINT outcome_reason_stated CHECK (outcome_reason <> ''),
  CONSTRAINT chain_length_positive CHECK (chain_length >= 1),
  CONSTRAINT digests_are_sha256 CHECK (
    length(ancestor_canon_sha256) = 64 AND length(descendant_canon_sha256) = 64
  ),
  INDEX by_class (run_id, kind, class_id),
  INDEX survivors (run_id, success) STORING (class_id, fixture_id, outcome_reason)
);
