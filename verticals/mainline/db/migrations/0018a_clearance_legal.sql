-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- MAINLINE · 0018a_clearance_legal.sql
-- CREATE TABLE mainline.clearance_legal — the typed clearance lattice
--
-- MI: MI11
-- I: I10
-- COUNSEL-GATED: no
-- RATIONALE: The legal set of clearing verdicts is a function of ancestral severity, and it
--            is versioned data with a named approver rather than code. That is what makes
--            disagreeing with it an amendment carrying a signature instead of a pull
--            request. A disposition composite-foreign-keys here, so a verdict outside the
--            lattice is 23503 naming this table, for every writer.
--
-- @rendered-by  trappoint render
-- @template     packages/trappoint-sql/templates/0018_clearance_legal.sql.j2
-- @binding      verticals/mainline/vertical.toml
-- DO NOT EDIT. `trappoint render --check` is a zero-diff assertion in CI, so a
-- hand edit here is a red build, not a silent divergence.
--
-- The primary key IS the mechanism. (virulence, kind) is the foreign-key target a
-- disposition points at, so a cell that does not exist is a verdict that cannot be
-- recorded — not a verdict that is recorded and flagged.
--
-- min_signer_rank is a floor, not a suggestion: the disposition projects the signer's
-- LIVE rank from `person` and compares it here, so a client that supplies its own rank
-- is overwritten before the comparison happens.
--
-- max_ttl_hours NULL means the verdict does not expire. A non-NULL value means bounded,
-- and bounded means bounded: the expiry is enforced, not merely present.

CREATE TABLE mainline.clearance_legal (
  virulence          mainline.virulence_class NOT NULL,
  kind               mainline.disposition_kind NOT NULL,
  req_compensating   BOOL NOT NULL DEFAULT false,
  req_second_signer  BOOL NOT NULL DEFAULT false,
  req_foreign_org    BOOL NOT NULL DEFAULT false,
  req_predicate      BOOL NOT NULL DEFAULT false,
  req_reassert       BOOL NOT NULL DEFAULT false,
  min_signer_rank    INT2 NOT NULL DEFAULT 1,
  max_ttl_hours      INT4 NULL,
  policy_version     STRING NOT NULL,
  approved_by_sub    STRING NOT NULL,
  approved_at        TIMESTAMPTZ NOT NULL,
  CONSTRAINT clearance_rank_range CHECK (min_signer_rank BETWEEN 1 AND 9),
  CONSTRAINT clearance_ttl_positive CHECK (max_ttl_hours IS NULL OR max_ttl_hours > 0),
  CONSTRAINT pk_clearance_legal PRIMARY KEY (virulence, kind)
);
