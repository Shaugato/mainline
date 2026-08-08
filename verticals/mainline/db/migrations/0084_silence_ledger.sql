-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- MI: MI01, MI17
-- I: I01, I13
-- COUNSEL-GATED: no
-- RATIONALE: This is the answer to the plaintiff's actual question — *your system knew about event X and did not show it* — and without the table the answer is silence plus an adverse inference; `reason` is a closed vocabulary because a free-text reason column is a way to write "other" forever and "other" is not a defence.
--
-- migration:  0084_silence_ledger
-- band:       0080-0089z · recall · AUTHORED, allocated by
--             verticals/mainline/db/migrations.allocation.toml (MR-6 lock 1)
-- domain:     recall
-- statements: 1
-- invariants: MI01 (append-only; the mutation guard is `fn_refuse_mutation`, §5.11),
--             MI17 (every silenced candidate is counted in the conserved partition)
-- source:     ARCHITECTURE.md §5.7 (verbatim; index declared inline per DM-6)
-- requires:   0002 CREATE SCHEMA mainline_meas (RENDERED; template 0001_schemas.sql.j2 —
--             corrected 2026-08-08: `0003` is now the AUDIT schema, so the old citation was
--             not merely stale, it named the wrong schema)
-- sqlstate:   P0001 on UPDATE/DELETE · 23514 on the closed `source`/`reason` vocabularies
-- forward-only; no .down.sql exists at or below the protected floor (DM-14). Under MR-5 there
--             is no .up.sql either: the suffix named a counterpart that is illegal by
--             construction.
--
-- THE LEDGER IS THE ANSWER TO THE PLAINTIFF'S ACTUAL QUESTION — *your system knew about event X
-- and did not show it*. Without this table the answer is silence plus an adverse inference.
-- With it: *it scored 0.31 against a threshold of 0.45, calibrated on a temporally-blocked gold
-- set under a documented severity-graded policy; here is the calibration commit and its author.*
--
-- Its dark side is stated rather than discovered: this is a complete list of every warning the
-- system chose not to give, with the arithmetic attached. Three controls make that survivable,
-- one of them a database constraint so the claim is provable rather than promised —
-- `bonded_fatalities_all_blocking` (0081); τ is never settable by an operational user (it is a
-- calibration artefact with its own commit, author, gold set and anchor, enforced by
-- `fn_recall_policy_anchored`); and the ledger stays in the UNPRIVILEGED measurement zone,
-- because its evidentiary value comes precisely from being a contemporaneous business record
-- made in the ordinary course of business.
--
-- `reason` is the closed D10 vocabulary. A free-text reason column is a way to write "other"
-- forever, and "other" is not a defence.

CREATE TABLE mainline_meas.silence_ledger (
  silence_id   UUID   NOT NULL DEFAULT gen_random_uuid(),
  site_id      UUID   NOT NULL,
  source       STRING NOT NULL CHECK (source IN ('recall','fleet_appraisal','severity_downgrade',
    'closure_truncation','dedup','delta_neutral','blame_lapse','patrol_suppression',
    'ring_exclusion','boundary_unmodelled')),
  reason       STRING NOT NULL CHECK (reason IN ('below_tau','model_refusal','dedup_sibling',
    'cap_exceeded','truncated','abstained','bounded_negative','unreachable')),   -- D10
  subject_kind STRING NOT NULL,
  subject_id   UUID   NOT NULL,
  severity     INT2   NOT NULL,
  score        FLOAT8 NULL,
  threshold    FLOAT8 NULL,
  arithmetic   JSONB  NOT NULL,                 -- components, model version, τ
  policy_version STRING NULL,
  at           TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT silence_ledger_pk PRIMARY KEY (silence_id),
  CONSTRAINT silence_sev_range CHECK (severity BETWEEN 0 AND 5),
  INDEX sl_by_subject (site_id, subject_id, at DESC)
);
