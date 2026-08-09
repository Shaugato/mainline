-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- MAINLINE · 0058_blocking_check.sql
-- CREATE TABLE mainline.blocking_check — the obligation the gate counts
--
-- MI: MI25, MI02, MI30
-- I: I02
-- COUNSEL-GATED: no
-- RATIONALE: The row every refusal in this product is ultimately a consequence of. Its
--            severity and virulence are projections of the blame closure rather than
--            inputs, so the agent that proposes an obligation cannot talk it down; and its
--            identity is a server-computed digest over coalesce sentinels rather than a
--            composite unique index, because NULLs are distinct in a unique index and six
--            of the eight origins leave a nullable identity column empty.
--
-- @rendered-by  trappoint render
-- @template     packages/trappoint-sql/templates/0058_blocking_check.sql.j2
-- @binding      verticals/mainline/vertical.toml
-- DO NOT EDIT. `trappoint render --check` is a zero-diff assertion in CI, so a
-- hand edit here is a red build, not a silent divergence.
--
-- @projects blocking_check.severity, blocking_check.virulence, blocking_check.closure_gen
-- @authority mainline.clause_blame_current (clause_uuid, as_of_commit) <= NEW (clause_uuid, commit_id)
-- @on_missing raise
--
-- SUBJECT-POLYMORPHIC, over the 2 gated subject(s) this binding declares:
--   permit -> mainline.permit (permit_id)
--   change_request -> mainline.change_request (cr_id)
--
-- Three constraints hold the polymorphism together and each catches a different lie:
--
--   exactly_one_subject   an obligation belongs to ONE subject. A row naming both a
--                         permit and a change request would be counted twice and
--                         cleared once (case CF-41).
--   subject_matches       the discriminator agrees with the column that is populated.
--                         Without it, subject_kind='permit' with only cr_id set makes
--                         every by-kind aggregate quietly wrong while every foreign key
--                         is satisfied.
--   bc_subject_kind_known the discriminator is drawn from the declared set, so a typo
--                         is 23514 at write time rather than a row no counter trigger
--                         ever visits.
--
-- WHY THE SUBJECT COLUMNS ARE NULLABLE AND NOT A SINGLE `subject_id`. A single column
-- would need either no foreign key at all — losing the guarantee that an obligation
-- names a subject that exists — or a polymorphic one, which does not exist in SQL.
-- CockroachDB enforces a foreign key only when every column of it is non-NULL (MATCH
-- SIMPLE), so a nullable column per kind gives exactly one enforced reference per row
-- and no enforcement on the other. That is ruling D1's mechanism, applied here.
--
-- fk_check_version IS WHAT MAKES A DISPOSITION UNINHERITABLE ACROSS A REVISION. The
-- check names (clause_uuid, commit_id), so a new version of a clause is a DIFFERENT
-- foreign-key target: it materialises a NEW obligation with a new check_id, and the
-- disposition signed against the old one cannot reach it. Carrying a clearance forward
-- across an edit is not forbidden by policy here; it is unrepresentable.
--
-- site_id CARRIES NO FOREIGN KEY, DELIBERATELY. A site table is vertical content — the
-- object test in MR-1 puts it outside the substrate — and a substrate table that
-- referenced it could not render for a binding that organises its estate differently.
-- The column is NOT NULL because every obligation belongs to somewhere; which relation
-- names that somewhere is the vertical's business.
--
-- materialised_at IS THE SERVER CLOCK and is never supplied by the writer. Deliberation
-- time and the open-obligation window are both derived from it, and a client-supplied
-- timestamp is a client-supplied deliberation measurement.

CREATE TABLE mainline.blocking_check (
  check_id           UUID NOT NULL DEFAULT gen_random_uuid(),
  subject_kind       STRING NOT NULL,
  permit_id          UUID NULL REFERENCES mainline.permit (permit_id),
  cr_id              UUID NULL REFERENCES mainline.change_request (cr_id),
  site_id            UUID NOT NULL,
  clause_uuid        UUID NOT NULL,
  commit_id          BYTES NOT NULL,
  precursor_event_id UUID NULL REFERENCES mainline.event (event_id),
  origin             STRING NOT NULL,
  -- ▼ PROJECTIONS. Overwritten by fn_check_project from mainline.clause_blame_current.
  --   NEVER inputs (finding S1, invariant MI25). See the @authority banner above.
  severity           INT2 NOT NULL,
  virulence          mainline.virulence_class NOT NULL,
  closure_gen        INT8 NOT NULL,
  -- ▲
  control_delta      mainline.control_delta NULL,
  recall_run_id      UUID NULL,
  evidence_summary   STRING NOT NULL,
  materialised_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  -- GT-13 PASS (v26.2.5): digest() is legal inside a STORED generated column, so
  -- the SERVER computes the obligation's identity and the inserter cannot choose it.
  dedupe_key         BYTES AS (digest(
                         coalesce(permit_id::STRING, '-') || '|' ||
                         coalesce(cr_id::STRING, '-') || '|' ||
                         clause_uuid::STRING || '|' ||
                         encode(commit_id, 'hex') || '|' ||
                         coalesce(precursor_event_id::STRING, '-') || '|' ||
                         origin, 'sha256')) STORED,
  CONSTRAINT bc_subject_kind_known
    CHECK (subject_kind IN ('permit', 'change_request')),
  CONSTRAINT bc_origin_known
    CHECK (origin IN ('blame_ancestry', 'weaken_over_blood', 'identity_residue', 'drift_finding', 'fleet_conflict', 'discordance_warrant', 'severity_downgrade', 'recall_probabilistic')),
  CONSTRAINT bc_severity_range CHECK (severity BETWEEN 0 AND 5),
  CONSTRAINT bc_evidence_summary_stated CHECK (evidence_summary <> ''),
  CONSTRAINT bc_commit_id_is_sha256 CHECK (length(commit_id) = 32),
  CONSTRAINT exactly_one_subject
    CHECK ((permit_id IS NULL) <> (cr_id IS NULL)),
  CONSTRAINT subject_matches
    CHECK ((subject_kind = 'permit' AND permit_id IS NOT NULL)
        OR (subject_kind = 'change_request' AND cr_id IS NOT NULL)),
  CONSTRAINT fk_check_version FOREIGN KEY (clause_uuid, commit_id)
    REFERENCES mainline.clause_version (clause_uuid, commit_id),
  UNIQUE (dedupe_key),
  CONSTRAINT pk_blocking_check PRIMARY KEY (check_id)
);
