-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- MI: MI01
-- I: I17
-- COUNSEL-GATED: no
-- RATIONALE: A published residual-risk number that cannot be traced to the code that produced it is a number nobody can be held to. This row carries the harness version, the catalogue digest, the operator-source fingerprint, the identity-policy digest and every component version, so a figure quoted in a submission, a video or a court can be re-derived from committed bytes or shown to be unreproducible.
--
-- migration:  0049y_meas_mutation_run
-- domain:     algorithms
-- band:       0049a-0049z · algorithms · AUTHORED, allocated by
--             verticals/mainline/db/migrations.allocation.toml (MR-6 lock 1), which grants the
--             letter space of 0049 to the algorithms domain EXPLICITLY AND EXCLUSIVELY as the
--             algorithms table annexe.
-- statements: 1
-- invariants: MI01 — evidentiary tables are append-only (welded by 0149y)
--             I17  — a published measurement states its own provenance
-- source:     docs/leads/algorithms.md §2 MUTATION RATCHET, §8 R-A1 ·
--             BUILD_PLAN.md K3 exit criteria 1 and 3, K8
-- requires:   0002 schema mainline_meas
-- sqlstate:   23514 on any of the six shape CHECKs · P0001 on UPDATE or DELETE (0149y)
-- forward-only; no .down.sql exists at or below the protected floor (DM-14). Under MR-5 there
--             is no .up.sql either.
--
-- ═════════════════════════════════════════════════════════════════════════════════════════════
-- WHY THIS FILE IS 0049y AND NOT 0209
-- ═════════════════════════════════════════════════════════════════════════════════════════════
-- The worker brief for `mutation-ratchet` names `0209_meas_mutation.sql`. That number does not
-- exist. The migration reconciliation ruling of 2026-08-08 — reproduced word for word in five
-- lead plans, including `docs/leads/algorithms.md` — REVOKES the `0200-0219` annexe in whole,
-- marks `0200` and above UNALLOCATED, and makes `trappoint migrate lint` rule B refuse any file
-- that claims a number no band grants. `docs/leads/algorithms.md` names this exact object among
-- the ones that are "unwritten and unnumbered … they take their numbers from the three bands
-- above when they are written". The three bands are `0049a-0049z`, `0150-0154`, and slices of
-- `0140-0149`. A `CREATE TABLE` belongs in the table space, so it takes a letter of `0049`.
--
-- `y` and `z` rather than `b` and `c`: this band is granted to the algorithms DOMAIN, not to one
-- worker, and four other objects in it (`identity_assignment`, `cbm_account`, `commutation_edge`
-- and their companions) are still unwritten by workers building in parallel. Taking the tail of
-- the band leaves the head free for the objects that have to sort BEFORE the gate, and a
-- measurement table has no ordering constraint against anything: it references nothing and
-- nothing references it.
--
-- ═════════════════════════════════════════════════════════════════════════════════════════════
-- WHAT THIS TABLE IS, IN ONE SENTENCE
-- ═════════════════════════════════════════════════════════════════════════════════════════════
-- One row per execution of the MUTATION RATCHET: the KILL and SURVIVE catalogues run against the
-- historical fixture revisions, with the Wilson-bounded rates and the exact provenance of the
-- code that produced them.
--
-- ── IT MEASURES. IT DOES NOT GATE. ───────────────────────────────────────────────────────────
-- Nothing reads this table to decide anything. No `permit` column is projected from it, no
-- `blocking_check` is materialised by it, no merge consults it. `docs/leads/algorithms.md` §2
-- records the MUTATION RATCHET's enforcement as "(measures; never gates)" and §8 R-A1 declines to
-- argue delta false negatives away, electing to publish them instead. A number that could stop a
-- merge would acquire an incentive to be high, and the whole value of this one is that it is
-- allowed to be bad.
--
-- ── EVERY RATE IS A WILSON LOWER BOUND ───────────────────────────────────────────────────────
-- `kill_rate_wilson_lower` is the claim; `kill_rate_point` sits beside it and is not. Three of
-- three killed is a point estimate of 1.0 and a 95 % lower bound of 0.44, and publishing 1.0
-- there is not optimism — it is a false statement about how much evidence exists. The interval
-- is computed by `mainline_mutation.wilson`, six lines of arithmetic with the preimage written
-- out in its docstring, deliberately not `statsmodels`: a bound whose derivation nobody in the
-- room can check by hand is a bound that does not survive cross-examination.
--
-- ── THE FIVE PROVENANCE COLUMNS, AND WHAT EACH ONE CATCHES ───────────────────────────────────
--   harness_version       the runner and the operators, bumped by hand
--   catalogue_sha256      the catalogue declaration, the fixture revisions and the paraphrase
--                         cassettes, digested together with length prefixes. Moves when the
--                         CLAIM moves: a class added, a magnitude changed, a fixture edited
--   operator_fingerprint  the SOURCE TEXT of every registered operator. This is what makes
--                         "traceable to the code that produced it" literally true rather than a
--                         promise about discipline — an operator edited without a version bump
--                         still moves this digest
--   policy_sha256         `StageBands.fingerprint()`, decision D11. Retro-tuning the matcher's
--                         accept bands to make a survival rate look better moves it, exactly as
--                         M3 makes tuning tau visible
--   lattice_rule_fingerprint  the four hand-authored decision tables behind the nine rules. A
--                         verdict computed under a quietly-edited comparator table is visibly a
--                         verdict from a different lattice
--
-- ── `disabled_lattice_rules` IS THE RED-BEFORE-GREEN COLUMN ──────────────────────────────────
-- PL-2: a harness that has only ever reported a kill rate of 1.0 has not been observed to assert
-- anything. The nightly workflow runs TWO arms — intact, and crippled with `R1_DEONTIC` switched
-- off — and this column is what distinguishes them in the record. A crippled run whose kill rate
-- did NOT fall would mean the harness was not measuring the lattice at all, and the pair of rows
-- is what makes that checkable years later. `arm_is_consistent` refuses a row that claims
-- 'crippled' with no rule named, or 'intact' with one.
--
-- ── HONEST LIMITS, STATED HERE BECAUSE THIS IS WHERE A NUMBER IS QUOTED FROM ──────────────────
--   * `path_b_consulted` is FALSE on every row this harness writes. Path B (the LLM oracle) may
--     only ever RAISE a verdict's force, so the published figure is a LOWER BOUND on the whole
--     system's detection and not an estimate of it.
--   * `residue_source` names a STAND-IN. Worker W8's `margin-assignment` had not landed when
--     this harness was written, so residue is derived by `mainline_mutation.residue` from the
--     same authoritative facts. No figure here is a measurement of W8's implementation.
--   * `paraphrase_provenance` is 'hand-authored'. AWS credentials are not valid (PL-3) and
--     decision D12 keeps the live Bedrock path out of CI, so the adversarial-paraphrase mutants
--     are what a competent adversary WOULD write, not a recording of what one did.
--   * The seed is stored because the run is a pure function of it and of committed bytes. A
--     figure that could not be reproduced from a recorded seed would be an anecdote.

CREATE TABLE mainline_meas.mutation_run (
  run_id            UUID   NOT NULL DEFAULT gen_random_uuid(),
  started_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  seed              INT8   NOT NULL,          -- the run is a pure function of this
  arm               STRING NOT NULL,          -- 'intact' | 'crippled'
  disabled_lattice_rules STRING[] NOT NULL DEFAULT ARRAY[]::STRING[],

  -- provenance: five digests and a version, each catching a different edit
  harness_version   STRING NOT NULL,
  catalogue_sha256  STRING NOT NULL,
  operator_fingerprint STRING NOT NULL,
  policy_sha256     STRING NOT NULL,
  lattice_rule_fingerprint STRING NOT NULL,

  -- component versions, so a figure names the whole pipeline that produced it
  canon_version     INT4   NOT NULL,
  cat_extractor_version STRING NOT NULL,
  lattice_version   STRING NOT NULL,
  minhash_version   INT4   NOT NULL,
  rescore_version   STRING NOT NULL,
  registry_encoding_version INT4 NOT NULL,

  -- KILL: control mutations that must be detected
  kill_trials       INT4   NOT NULL,
  kill_killed       INT4   NOT NULL,
  kill_rate_wilson_lower DECIMAL(9,6) NOT NULL,   -- THE CLAIM
  kill_rate_point        DECIMAL(9,6) NOT NULL,   -- not the claim
  kill_rate_wilson_upper DECIMAL(9,6) NOT NULL,

  -- SURVIVE: identity-preserving reformats that must NOT be detected
  survive_trials    INT4   NOT NULL,
  survive_preserved INT4   NOT NULL,
  survive_rate_wilson_lower DECIMAL(9,6) NOT NULL,   -- THE CLAIM
  survive_rate_point        DECIMAL(9,6) NOT NULL,
  survive_rate_wilson_upper DECIMAL(9,6) NOT NULL,
  false_identity_change_rate DECIMAL(9,6) NOT NULL,  -- a POINT estimate, and labelled so
  false_weaken_rate          DECIMAL(9,6) NOT NULL,  -- likewise

  confidence        STRING NOT NULL,          -- '0.90' | '0.95' | '0.99'
  skipped_pairings  INT4   NOT NULL DEFAULT 0,

  -- the honesty columns. Every one of them is FALSE-or-a-name on every row this
  -- harness writes today, and each is a column rather than a comment so that a
  -- future run in which it changed is visibly a different measurement.
  path_b_consulted  BOOL   NOT NULL DEFAULT false,
  residue_source    STRING NOT NULL,
  paraphrase_provenance STRING NOT NULL,
  cbm_exercised     BOOL   NOT NULL DEFAULT false,
  cascade_s4_driven BOOL   NOT NULL DEFAULT false,

  artefact_path     STRING NULL,              -- the dated JSON under evidence/mutation/

  CONSTRAINT mutation_run_pk PRIMARY KEY (run_id),
  CONSTRAINT arm_closed CHECK (arm IN ('intact', 'crippled')),
  -- A row claiming 'crippled' with no rule named would make the red-before-green
  -- pair unreadable, and a row claiming 'intact' with a rule disabled would
  -- publish a crippled number under the production label.
  CONSTRAINT arm_is_consistent CHECK (
    (arm = 'crippled') = (array_length(disabled_lattice_rules, 1) IS NOT NULL)
  ),
  CONSTRAINT kill_counts_sane CHECK (kill_killed >= 0 AND kill_killed <= kill_trials),
  CONSTRAINT survive_counts_sane
    CHECK (survive_preserved >= 0 AND survive_preserved <= survive_trials),
  -- The lower bound can never exceed the point estimate, and the point estimate
  -- can never exceed the upper bound. A row that violated this would be a
  -- transcription error in the one direction that flatters the product.
  CONSTRAINT kill_interval_ordered CHECK (
    kill_rate_wilson_lower <= kill_rate_point AND kill_rate_point <= kill_rate_wilson_upper
  ),
  CONSTRAINT survive_interval_ordered CHECK (
    survive_rate_wilson_lower <= survive_rate_point
    AND survive_rate_point <= survive_rate_wilson_upper
  ),
  CONSTRAINT confidence_closed CHECK (confidence IN ('0.90', '0.95', '0.99')),
  CONSTRAINT digests_are_sha256 CHECK (
    length(catalogue_sha256) = 64
    AND length(operator_fingerprint) = 64
    AND length(policy_sha256) = 64
    AND length(lattice_rule_fingerprint) = 64
  ),
  CONSTRAINT residue_source_stated CHECK (residue_source <> ''),
  CONSTRAINT paraphrase_provenance_stated CHECK (paraphrase_provenance <> ''),
  INDEX by_started (started_at DESC),
  INDEX by_catalogue (catalogue_sha256, started_at DESC)
);
