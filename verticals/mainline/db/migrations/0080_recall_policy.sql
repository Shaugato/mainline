-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- MI: MI18
-- I: I07
-- COUNSEL-GATED: no
-- RATIONALE: τ is a calibration artefact, not a setting: the row carries its own calibration-set digest, author and signature, so the answer to *why did the system not surface event X* is a commit with a name on it rather than a config value with no history.
--
-- migration:  0080_recall_policy
-- band:       0080-0089z · recall · AUTHORED, allocated by
--             verticals/mainline/db/migrations.allocation.toml (MR-6 lock 1)
-- domain:     recall
-- statements: 1
-- invariants: MI18 — a recall runs only under an anchored, cosigned policy version.
-- source:     ARCHITECTURE.md §5.7 (verbatim) · S24
-- requires:   0002 CREATE SCHEMA mainline_meas (RENDERED; template 0001_schemas.sql.j2 —
--             corrected 2026-08-08: `0003` is now the AUDIT schema, so the old citation was
--             not merely stale, it named the wrong schema)
-- sqlstate:   P0001 via 0112/0136 when a run cites an unanchored policy
-- forward-only; no .down.sql exists at or below the protected floor (DM-14). Under MR-5 there
--             is no .up.sql either: the suffix named a counterpart that is illegal by
--             construction.
--
-- τ IS A CALIBRATION ARTEFACT, NOT A SETTING. This is the difference between "we chose a
-- threshold" and "a threshold was chosen for us by a gold set, an author and a signature". The
-- row carries its own calibration-set digest, its author and its signature, so the answer to
-- *why did the system not surface event X* is a commit with a name on it rather than a config
-- value with no history.
--
-- `anchored_tree_size` is the S24 mechanism: the policy's commitment must be INSIDE a cosigned
-- ledger checkpoint before any run may cite it. Retro-fitting a policy after the fact — the
-- cheapest attack on a silence ledger — then requires forging a checkpoint that has already
-- left the trust boundary. It is NULL until the anchor lands, and `fn_recall_policy_anchored`
-- (0112) refuses every run that cites a policy while it is NULL.
--
-- 0085 adds `calibrator JSONB NOT NULL DEFAULT '{}'` (D8: monotone step-function knots, never a
-- pickle — `p_relevant` is an exhibit and an exhibit must be re-evaluable by a stranger) and
-- `thymogate_certificate_id UUID NULL` (D14, M5). That column's FK onto
-- `mainline_meas.thymogate_certificate` is the deferred half of a two-table cycle and lands in
-- 0086a, after the table it references is created in 0086.

CREATE TABLE mainline_meas.recall_policy (
  policy_version STRING NOT NULL,
  taxonomy_ver   INT4   NOT NULL,
  embed_model    STRING NOT NULL,
  gen_model      STRING NOT NULL,
  prompt_version STRING NOT NULL,
  beam_size      INT4   NOT NULL,
  tau            JSONB  NOT NULL,              -- severity-graded admission thresholds
  arms           JSONB  NOT NULL,
  calibration_set_sha256 BYTES NOT NULL,
  author_sub     STRING NOT NULL,
  signature      BYTES  NOT NULL,
  anchored_tree_size INT8 NULL,                -- must be in a cosigned checkpoint BEFORE use
  anchored_at    TIMESTAMPTZ NULL,
  committed_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT recall_policy_pk PRIMARY KEY (policy_version),
  CONSTRAINT anchor_is_paired
    CHECK ((anchored_tree_size IS NULL) = (anchored_at IS NULL)),
  CONSTRAINT beam_positive CHECK (beam_size >= 1)
);
