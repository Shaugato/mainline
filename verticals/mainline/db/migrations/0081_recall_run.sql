-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- migration:  0081_recall_run
-- domain:     recall
-- statements: 1
-- invariants: MI16 (`bonded_fatalities_all_blocking`), MI17 (`candidates_conserved`),
--             MI18 (enforced by 0112/0136 on this table's INSERT)
-- source:     ARCHITECTURE.md §5.7 (verbatim; one index added — see RD-2 below)
-- requires:   0080 mainline_meas.recall_policy
-- sqlstate:   23514 on either conservation CHECK · P0001 on an unanchored policy
-- forward-only; no .down.sql exists at or below the protected floor (DM-14).
--
-- MI17, the silence conservation law, is one line of arithmetic:
--     n_candidates = n_blocking + n_advisory + n_silenced + n_deduped
-- and it is the reason the silence ledger cannot be quietly short. A candidate that was
-- retrieved and then vanished from the accounting has nowhere to go: the row will not insert.
--
-- MI16 is the positive invariant — the hard one, because it asserts that something MUST be
-- there rather than that something must not. `n_bonded_sev5_blocking = n_bonded_sev5` refuses
-- any run row that recognises a bonded fatality without a blocking obligation for it.
--
-- RD-1 · HOW THE TWO BONDED COUNTERS MOVE. The CHECK is evaluated at every statement, so the
-- pair must be equal at every statement boundary; there is therefore no ordering in which one
-- counter is incremented alone. `mainline.fn_bonded_sev5` (0113) consequently moves BOTH, in
-- one UPDATE, on every blocking check that lands whose precursor is a bonded severity-5 event —
-- deriving the fact that it IS one from `mainline.event_bond` ⋈ `mainline.event`, never from
-- the inserter. The consequences are exactly what MI16 wants:
--   · an agent cannot open a run declaring bonded fatalities it did not materialise as checks
--     (23514, refused at INSERT — this is RC-05);
--   · an agent cannot lower the blocking count later, because the column is only ever written
--     by a trigger firing on an append-only table;
--   · and with the trigger DROPPED the CHECK still refuses the lying row, which is the
--     unwelding case in tests/integration/recall_schema/test_unweld.py.
--
-- RD-2 · `INDEX by_permit` is added to §5.7's verbatim DDL. `fn_bonded_sev5` looks the run up
-- by `permit_id` inside an AFTER INSERT trigger on `blocking_check`, which is on the
-- check-materialisation path; an unindexed lookup there is a p99 defect, not a preference.

CREATE TABLE mainline_meas.recall_run (
  run_id         UUID   NOT NULL DEFAULT gen_random_uuid(),
  permit_id      UUID   NOT NULL,
  site_id        UUID   NOT NULL,
  corpus_commit  BYTES  NOT NULL,
  policy_version STRING NOT NULL REFERENCES mainline_meas.recall_policy (policy_version),
  index_plan_digest BYTES NOT NULL,             -- hash of the EXPLAIN output ACTUALLY observed
  index_generation  STRING NOT NULL,
  n_candidates   INT4   NOT NULL,
  n_blocking     INT4   NOT NULL,
  n_advisory     INT4   NOT NULL,
  n_silenced     INT4   NOT NULL,
  n_deduped      INT4   NOT NULL,
  arms_degraded  BOOL   NOT NULL DEFAULT false,
  -- S10: "a fatality in your fonds is always recalled" as a POSITIVE invariant.
  n_bonded_sev5  INT4   NOT NULL DEFAULT 0,     -- trigger-maintained (0113), never an input
  n_bonded_sev5_blocking INT4 NOT NULL DEFAULT 0,
  started_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  latency_ms     INT4   NULL,
  CONSTRAINT recall_run_pk PRIMARY KEY (run_id),
  CONSTRAINT candidates_conserved
    CHECK (n_candidates = n_blocking + n_advisory + n_silenced + n_deduped),
  CONSTRAINT bonded_fatalities_all_blocking
    CHECK (n_bonded_sev5_blocking = n_bonded_sev5),
  INDEX by_permit (permit_id, started_at DESC)
);
