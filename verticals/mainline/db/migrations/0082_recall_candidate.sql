-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- migration:  0082_recall_candidate
-- domain:     recall
-- statements: 1
-- invariants: MI17 (this table is the partition `candidates_conserved` counts),
--             MI25 (the projection principle: `severity` is projected, never supplied)
-- source:     ARCHITECTURE.md §5.7 (verbatim) · S10
-- requires:   0081 mainline_meas.recall_run · 0033 mainline.event
-- sqlstate:   P0001 via 0139 when the event does not exist
-- forward-only; no .down.sql exists at or below the protected floor (DM-14).
--
-- `severity` is PROJECTED from `mainline.event.severity_gate` by `mainline.fn_candidate_project`
-- (0139) and a missing event RAISEs. The reason is S10 and it is not hypothetical: severity is
-- what lowers the evidence bar in Severity-Graded Admission (τ(5)=0.35 … τ(1)=0.85). An agent
-- that could write `severity` could downgrade a fatality into the band where its own score
-- falls below τ, and the resulting silence-ledger row would read as a well-calibrated judgement
-- rather than as the laundering it was. Projection makes that arithmetic unreachable.
--
-- `p_relevant` is calibrated (D8, isotonic knots in `recall_policy.calibrator`). A raw cosine
-- must never reach a human: "0.83" means nothing to a supervisor and less to a court.
--
-- The table is append-only in the deployed schema (`fn_refuse_mutation`, §5.11 — owned by
-- `dm-functions-triggers`), because a candidate row is the contemporaneous business record that
-- answers the plaintiff's question, and a mutable one answers nothing.

CREATE TABLE mainline_meas.recall_candidate (
  run_id     UUID   NOT NULL REFERENCES mainline_meas.recall_run (run_id),
  event_id   UUID   NOT NULL,
  rank       INT4   NOT NULL,
  severity   INT2   NOT NULL,                   -- PROJECTED from event.severity_gate (S10)
  features   JSONB  NOT NULL,
  p_relevant FLOAT8 NOT NULL,                   -- calibrated. Raw cosine never reaches a human.
  tau_applied FLOAT8 NOT NULL,
  outcome    STRING NOT NULL
    CHECK (outcome IN ('blocking','advisory','silenced','deduped')),
  CONSTRAINT recall_candidate_pk PRIMARY KEY (run_id, event_id),
  CONSTRAINT candidate_sev_range CHECK (severity BETWEEN 0 AND 5),
  CONSTRAINT p_relevant_is_a_probability CHECK (p_relevant >= 0.0 AND p_relevant <= 1.0)
);
