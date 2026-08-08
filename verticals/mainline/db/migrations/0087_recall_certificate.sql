-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- MI: MI17
-- I: I08
-- COUNSEL-GATED: no
-- RATIONALE: "We found nothing" is the single most dangerous output this system can produce, because it is indistinguishable to the reader from "there is nothing"; binding a null result to an index generation and a structural fingerprint is what makes the difference legible, and where it cannot be certified the verdict is UNDETERMINED.
--
-- migration:  0087_recall_certificate
-- band:       0080-0089z · recall · AUTHORED, allocated by
--             verticals/mainline/db/migrations.allocation.toml (MR-6 lock 1)
-- domain:     recall
-- statements: 1
-- invariants: MI17 (the certificate bounds what the conserved partition may be claimed to mean)
-- source:     BUILD_PLAN K4 (M4 CUE HORIZON) · docs/leads/recall.md §4 · ARCHITECTURE §5.7
-- requires:   0081 mainline_meas.recall_run
-- sqlstate:   23514 on `complete_needs_a_basis_that_can_establish_it`
-- forward-only; no .down.sql exists at or below the protected floor (DM-14). Under MR-5 there
--             is no .up.sql either: the suffix named a counterpart that is illegal by
--             construction.
--
-- M4 CUE HORIZON — THE CERTIFIED NULL. "We found nothing" is the single most dangerous output
-- this system can produce, because it is indistinguishable, to the person reading it, from
-- "there is nothing". This table is what makes the difference legible: a null result is bound
-- to an index generation and a structural fingerprint, and where it cannot be certified the
-- verdict is `UNDETERMINED` and PER MAY NOT CLAIM EXHAUSTION.
--
-- WHY THE FINGERPRINT IS THE ONLY STRUCTURAL TRIPWIRE HERE: `INSPECT` skips vector indexes.
-- Nothing else in the platform will tell us that a C-SPANN tree was rebuilt, re-partitioned or
-- silently degraded between the run that scored the corpus and the exhibit that quotes it.
-- `index_fingerprint` is computed by the recall orchestrator over the observable index
-- structure (generation, plan skeleton per arm, per-arm target counts and prefix spans) and a
-- later mismatch turns the certificate from evidence into a question. That is the correct
-- failure direction.
--
-- `complete_needs_a_basis_that_can_establish_it` is the constraint that keeps the product
-- honest under its own thesis: ANN is approximate, so an arms-based coverage basis can never
-- support a verdict of 'complete'. Only an exhaustive scan can. The database refuses the
-- overclaim rather than trusting the orchestrator not to make it.

CREATE TABLE mainline_meas.recall_certificate (
  certificate_id   UUID   NOT NULL DEFAULT gen_random_uuid(),
  run_id           UUID   NOT NULL REFERENCES mainline_meas.recall_run (run_id),
  index_generation STRING NOT NULL,
  index_fingerprint BYTES NOT NULL,             -- INSPECT skips vector indexes: this is the only
                                                -- structural tripwire we have
  coverage_basis   STRING NOT NULL CHECK (coverage_basis IN
    ('full_scan','index_arms','index_arms_plus_sweep','fingerprint_mismatch','unavailable')),
  verdict          STRING NOT NULL CHECK (verdict IN ('complete','partial','UNDETERMINED')),
  issued_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT recall_certificate_pk PRIMARY KEY (certificate_id),
  CONSTRAINT one_certificate_per_run_generation UNIQUE (run_id, index_generation),
  CONSTRAINT complete_needs_a_basis_that_can_establish_it
    CHECK (verdict <> 'complete' OR coverage_basis = 'full_scan')
);
