-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- MAINLINE · 0051_change_request.sql
-- CREATE TABLE mainline.change_request — the document branch is gated too (finding S16)
--
-- MI: MI30, MI03, MI04
-- I: I02, I03
-- COUNSEL-GATED: no
-- RATIONALE: The change request is a gated subject in exactly the sense the permit is, and
--            that identity is the thesis: the repository is the protected branch and the
--            permit is one of its refs. Its counters are projections, its four refusals are
--            independently named under R-3, and UNIQUE (cr_id, gate_epoch) gives the epoch
--            pin its foreign-key target, so a precursor arriving after a document merge is
--            refused by referential integrity rather than by a policy someone can edit.
--
-- @rendered-by  trappoint render
-- @template     packages/trappoint-sql/templates/0051_change_request.sql.j2
-- @binding      verticals/mainline/vertical.toml
-- DO NOT EDIT. `trappoint render --check` is a zero-diff assertion in CI, so a
-- hand edit here is a red build, not a silent divergence.
--
-- ── THE PROJECTED CROSS-ROW FACTS ────────────────────────────────────────────────
-- Written by a projection trigger from a declared authority relation, never by the
-- inserter (I02). A value a client supplies for one of these columns does not survive the
-- write, and absence of the authority row REFUSES rather than defaulting.
--
-- @projects   mainline.change_request.open_blocking
-- @projects   mainline.change_request.open_residue
-- @projects   mainline.change_request.open_conflicts
-- @projects   mainline.change_request.site_role
-- @on_missing raise
-- @maintained-by the projection band (functions 0100-0109, triggers 0120-0129)
--
-- Rendered SQL comments rather than template pragmas: the Authority Source Contract
-- (A-1) demands a keyed [[authority_source]] behind each pragma'd column, and a counter
-- is an aggregate over an [[obligation_source]], not a keyed lookup of one row. The
-- permit template carries the same note at length.
--
-- ── COLUMN NOTES ─────────────────────────────────────────────────────────────────
-- target_ref   the protected branch this change request wants to merge INTO. Deliberately
--              unconstrained by a foreign key even in a vertical that owns a ref relation:
--              a change request may legitimately name a branch that does not exist yet,
--              and refusing that write would move a workflow decision into the schema.
-- head_seq     the event chain's head, derived in-transaction and defended by the CAS on
--              cr_event; never allocated by a generator that commits outside the
--              transaction, because a gap in this chain must MEAN tampering.
-- gate_epoch   increments iff the gate OPENS. Pinned by epoch_pin_cr once the change
--              request merges, after which no obligation can be attached to it at all.
--
-- ── NO parent_cr_id, AND THAT IS NOT AN OVERSIGHT ────────────────────────────────
-- A permit forks: the declared remedy for a post-completion fact is to suspend the issued
-- permit and open a CHILD whose gate is cleared afresh, so the permit carries a parent
-- link. A change request does not fork — the remedy for a merged document change is a new
-- change request against the new head, which is an ordinary row with its own ref lineage
-- in the commit DAG. Inventing a parent column here would create a second, weaker lineage
-- beside the one the repository already keeps.

CREATE TABLE mainline.change_request (
  cr_id            UUID NOT NULL DEFAULT gen_random_uuid(),
  site_id          UUID NOT NULL,
  site_role        NAME NOT NULL,
  external_ref     STRING NOT NULL,
  ref_name         STRING NOT NULL,
  target_ref       STRING NOT NULL,
  state            mainline.subject_state NOT NULL DEFAULT 'draft',
  head_seq         INT8 NOT NULL DEFAULT 0,
  gate_epoch       INT8 NOT NULL DEFAULT 0,
  merged_commit    BYTES NULL,
  opened_at        TIMESTAMPTZ NOT NULL DEFAULT now(),

  -- ▼▼ PROJECTED CROSS-ROW FACTS. Trigger-written, never supplied. ▼▼
  open_blocking    INT8 NOT NULL DEFAULT 0,
  open_residue     INT8 NOT NULL DEFAULT 0,
  open_conflicts   INT8 NOT NULL DEFAULT 0,
  -- ▲▲

  CONSTRAINT cr_ctr_nonneg CHECK (
    open_blocking >= 0 AND
    open_residue >= 0 AND
    open_conflicts >= 0
  ),

  -- ▼▼ THE PRODUCT, MIRRORED. 4 independent refusals; each name is the exhibit. ▼▼
  CONSTRAINT cr_gate_closed_when_merged         CHECK (state <> 'merged' OR open_blocking = 0),
  CONSTRAINT cr_identity_conserved_when_merged  CHECK (state <> 'merged' OR open_residue = 0),
  CONSTRAINT cr_conflicts_resolved_when_merged  CHECK (state <> 'merged' OR open_conflicts = 0),
  CONSTRAINT cr_merge_evidence                  CHECK (state <> 'merged' OR merged_commit IS NOT NULL),
  -- ▲▲

  CONSTRAINT cr_ledger_nonneg       CHECK (head_seq >= 0 AND gate_epoch >= 0),
  CONSTRAINT cr_external_ref_stated CHECK (external_ref <> ''),
  CONSTRAINT cr_ref_name_stated     CHECK (ref_name <> ''),
  CONSTRAINT cr_target_ref_stated   CHECK (target_ref <> ''),
  CONSTRAINT cr_site_role_stated    CHECK (site_role <> ''),
  CONSTRAINT cr_commit_sized        CHECK (merged_commit IS NULL OR length(merged_commit) = 32),
  CONSTRAINT pk_change_request PRIMARY KEY (cr_id),
  -- The epoch pin's foreign-key target, mirroring the permit's. epoch_pin_cr is declared
  -- against this UNIQUE in migration 0071b.
  CONSTRAINT cr_epoch_target        UNIQUE (cr_id, gate_epoch),
  CONSTRAINT cr_external_ref_unique UNIQUE (site_id, external_ref)
);
