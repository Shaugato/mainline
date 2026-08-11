-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- MI: MI01, MI17
-- I: I01, I13
-- COUNSEL-GATED: yes (G0) · DEFAULT: conservative · ADR: docs/adr/0001-g0-counsel.md
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
-- ── THE COUNSEL GATE — CORRECTED 2026-08-10 ─────────────────────────────────────────────────
--
-- This file declared `COUNSEL-GATED: no`, and that was wrong on the record rather than merely
-- terse. ADR 0001 (docs/adr/0001-g0-counsel.md) lists five counsel-sensitive DDL files and
-- names this object among them:
--
--     | `0086 silence_ledger` | Ships **unprivileged** — treated as discoverable by default |
--
-- "Ships unprivileged" is a LEGAL posture, not a technical default. It is the shipped answer to
-- G0 question 2 — *does a system that also logs every precursor it declined to surface, with
-- the arithmetic attached, help or hurt the defence?* — and G0 was not sought, so the
-- pre-committed conservative reading is what executes. `db/ext/disposition_ext/
-- disposition_ext.toml` carries it as switch 3: `[silence] silence_ledger_zone =
-- "mainline_meas"`, `privileged = false`. The schema qualifier on the CREATE TABLE below IS
-- that switch's current value; changing it is answering a legal question, not tidying a zone.
--
-- The header is where the next editor of this file finds out that its placement was a decision.
-- Under `no`, a reviewer moving this table behind privilege — which reads, in discovery, as
-- concealment of the one exhibit whose evidentiary value comes precisely from being a
-- contemporaneous business record made in the ordinary course of business — would have had
-- nothing in front of them saying a gate existed. DM-17 made COUNSEL-GATED a linted key for
-- exactly that reason, and the long form is mandated so that `yes` says WHICH gate and what the
-- default is.
--
-- The SLOT is deliberately not what is gated. ADR 0001 and BUILD_PLAN §2.1 both cite `0086`;
-- the recall band landed this object at `0084` and `0086` is `thymogate_certificate`. The gate
-- is about the OBJECT, which is why
-- `tests/integration/schema/test_mi_disposition_gated.py::test_every_counsel_gated_object_declares_it`
-- resolves it by RELATION and would keep failing after somebody renumbered it.
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
