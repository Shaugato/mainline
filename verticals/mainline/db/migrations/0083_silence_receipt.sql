-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- migration:  0083_silence_receipt
-- domain:     recall
-- statements: 1
-- invariants: MI17 (the receipt commits to the partition MI17 conserves)
-- source:     ARCHITECTURE.md §5.7 (verbatim) · M3 Proof of Exhausted Recall
-- requires:   0081 mainline_meas.recall_run
-- sqlstate:   23514 on `boundary_sane`
-- forward-only; no .down.sql exists at or below the protected floor (DM-14).
--
-- PROOF OF EXHAUSTED RECALL — a cryptographically enforced privilege log. Because the candidate
-- leaves are SCORE-SORTED, disclosing `candidate_root`, θ, s, n and the boundary pair with their
-- inclusion paths establishes that every leaf beyond position s scored below θ — no item can be
-- hand-excluded without breaking sortedness — while revealing nothing about the suppressed
-- content itself.
--
-- WHAT IT DOES NOT PROVE, and this sentence ships in the schema because it must ship in every
-- exhibit: PER establishes exhaustion OF THE RETRIEVAL THAT RAN, not of the corpus. C-SPANN is
-- approximate and its trees mutate on every insert. `recall_run.index_generation` and
-- `index_plan_digest` are in the receipt's ancestry for exactly this reason, and 0087's CUE
-- HORIZON certificate carries the structural fingerprint. A proof that overclaims is worse than
-- no proof at all.
--
-- Leaf construction is fixed by recall D10: leaf = sha256(0x00 ‖ JCS({ord, event_id, score_q,
-- tau_applied, outcome})) with score_q = round(p_relevant × 10⁶) as an INTEGER; interior nodes
-- = sha256(0x01 ‖ L ‖ R). Integer quantisation is not fastidiousness — float formatting drift
-- would break sortedness, and sortedness is the entire force of the proof.

CREATE TABLE mainline_meas.silence_receipt (
  silence_receipt_id UUID NOT NULL DEFAULT gen_random_uuid(),
  run_id         UUID   NOT NULL REFERENCES mainline_meas.recall_run (run_id),
  permit_id      UUID   NOT NULL,
  corpus_root    BYTES  NOT NULL,
  candidate_root BYTES  NOT NULL,               -- Merkle over the SCORE-SORTED multiset
  theta          FLOAT8 NOT NULL,
  s              INT4   NOT NULL,
  n              INT4   NOT NULL,
  boundary_proof JSONB  NOT NULL,               -- inclusion paths for leaves s and s+1
  policy_version STRING NOT NULL,
  issued_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT silence_receipt_pk PRIMARY KEY (silence_receipt_id),
  CONSTRAINT boundary_sane CHECK (s >= 0 AND s <= n)
);
