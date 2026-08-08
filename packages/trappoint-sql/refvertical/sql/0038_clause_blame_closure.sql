-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: Apache-2.0
--
-- TRAPPOINT_REF · 0038_clause_blame_closure.sql
-- CREATE TABLE trappoint_ref.clause_blame_closure — THE AUTHORITY RELATION
--
-- MI: MI26
-- I: I05
-- COUNSEL-GATED: no
-- RATIONALE: HAND-WRITTEN, NOT RENDERED. This is the relation the reference binding's
--            first authority source points at, and the reason `trappoint-conform
--            --profile trappoint-ref` can be green with zero ancestry code in existence.
--            Isomorphic to ARCHITECTURE.md §5.4 in every respect a projection trigger
--            can observe: the primary key, max_severity, virulence, closure_gen and
--            truncated are named and typed identically, so a trigger rendered from a
--            kernel template runs unchanged against either vertical.
--
-- APPEND-ONLY, GENERATION-VERSIONED, MONOTONE (finding S2). Three properties, and each
-- one is load-bearing:
--
--   * PRIMARY KEY (clause_uuid, as_of_commit, closure_gen) — a recomputation is a new
--     generation, never an overwrite. The closure that armed a check last year is still
--     readable this year, which is what makes a diachronic gate diachronic.
--   * `truncated` — a closure that hit its depth or fan-out bound says so. A truncated
--     closure that reported itself complete would understate ancestral severity, and
--     understating severity is the one error direction with physical consequences.
--   * `computed_by` / `projector_ver` — every generation names the agent identity and
--     the code version that produced it. A mass rewrite is visible as a generation
--     count, not as a silent change of values.
--
-- The monotone guard, the append-only trigger and the `INSERT`-and-nothing-else grant
-- to the projector role are NOT here: they are trigger-band migrations owned by the
-- projection worker, and they render for this vertical from the same templates as for
-- any other. What this file owes them is a table of the right shape.

CREATE TABLE trappoint_ref.clause_blame_closure (
  clause_uuid     UUID   NOT NULL,
  as_of_commit    BYTES  NOT NULL,
  closure_gen     INT8   NOT NULL,
  site_id         UUID   NOT NULL,
  ancestor_events UUID[] NOT NULL,
  ancestor_count  INT4   NOT NULL,
  max_severity    INT2   NOT NULL,
  virulence       trappoint_ref.virulence_class NOT NULL,
  depth           INT4   NOT NULL,
  truncated       BOOL   NOT NULL DEFAULT false,
  computed_by     STRING NOT NULL,
  projector_ver   STRING NOT NULL,
  computed_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT closure_sev_range CHECK (max_severity BETWEEN 0 AND 5),
  CONSTRAINT closure_gen_positive CHECK (closure_gen >= 0),
  CONSTRAINT closure_depth_positive CHECK (depth >= 0),
  CONSTRAINT closure_count_positive CHECK (ancestor_count >= 0),
  CONSTRAINT fk_closure_version FOREIGN KEY (clause_uuid, as_of_commit)
    REFERENCES trappoint_ref.clause_version (clause_uuid, commit_id),
  CONSTRAINT pk_clause_blame_closure PRIMARY KEY (clause_uuid, as_of_commit, closure_gen)
);
