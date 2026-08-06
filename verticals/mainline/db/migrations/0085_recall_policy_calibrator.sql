-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- migration:  0085_recall_policy_calibrator
-- domain:     recall
-- statements: 1 (one ALTER TABLE, two ADD COLUMN subcommands)
-- invariants: MI18 (the policy row is the anchored artefact a run cites)
-- source:     docs/leads/recall.md D8 (calibrator) and D14 (THYMOGATE)
-- requires:   0080 mainline_meas.recall_policy
-- sqlstate:   —
-- forward-only; no .down.sql exists at or below the protected floor (DM-14).
--
-- D8 · THE CALIBRATOR IS SERIALISED AS MONOTONE STEP-FUNCTION KNOTS, NEVER AS A PICKLE.
-- `p_relevant` is an exhibit. A pickle is neither auditable nor safe to load, and an exhibit
-- that can only be interpreted by running the defendant's own binary is not an exhibit. The
-- knots are re-evaluable by a stranger in about twenty lines of code:
--     {"kind":"isotonic_knots","version":1,
--      "knots":[[0.00,0.01],[0.31,0.22],[0.52,0.61],[1.00,0.98]]}
-- with linear interpolation between knots and clamping outside them. The shape is validated by
-- the fusion worker's Pydantic model; the database's job is to make it a column with a history,
-- not to parse it.
--
-- D14 · `thymogate_certificate_id` IS NULLABLE AT K4 AND BECOMES NOT NULL AT K8. Negative
-- selection IS an evaluation: the panel is a corpus artefact and the certificate is emitted by
-- a harness run, precisely so that a tuned retriever cannot certify itself. The FK is added in
-- 0086 with the table it points at — the same deferred-cycle shape §18 already uses at 0171.

ALTER TABLE mainline_meas.recall_policy
  ADD COLUMN calibrator JSONB NOT NULL DEFAULT '{}'::JSONB,
  ADD COLUMN thymogate_certificate_id UUID NULL;
