-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: Apache-2.0
--
-- TRAPPOINT_REF · 0050_permit.sql
-- CREATE TABLE trappoint_ref.permit — the protected branch, and the refusals that guard its merge
--
-- MI: MI02, MI03, MI04, MI05, MI06
-- I: I02, I03
-- COUNSEL-GATED: no
-- RATIONALE: The permit is a protected branch and this row is its head. Every cross-row
--            obligation is projected onto a scalar column here by a trigger, and a plain-
--            column CHECK over that scalar then refuses the completing transition for every
--            writer, forever — which is the only form of the rule that survives a second
--            writer nobody anticipated. Six independently named CHECKs rather than one
--            counter because the constraint name is the courtroom exhibit (R-2), and UNIQUE
--            (permit_id, gate_epoch) because the epoch pin needs a foreign-key target:
--            without it a precursor arriving after the merge could be attached to an issued
--            permit and SERIALIZABLE would call that history perfectly legal.
--
-- @rendered-by  trappoint render
-- @template     packages/trappoint-sql/templates/0050_permit.sql.j2
-- @binding      packages/trappoint-sql/refvertical/vertical.toml
-- DO NOT EDIT. `trappoint render --check` is a zero-diff assertion in CI, so a
-- hand edit here is a red build, not a silent divergence.
--
-- ── THE PROJECTED CROSS-ROW FACTS ────────────────────────────────────────────────
-- Each column named below is a MATERIALISED CONFLICT, not a cache. It is written by a
-- projection trigger from a declared authority relation and never by the inserter; a
-- value a client supplies for one of these columns does not survive the write (I02).
-- Absence of the authority row REFUSES — it does not default, infer, or admit-and-flag.
--
-- @projects   trappoint_ref.permit.open_blocking
-- @projects   trappoint_ref.permit.open_residue
-- @projects   trappoint_ref.permit.open_conflicts
-- @projects   trappoint_ref.permit.open_warrants
-- @projects   trappoint_ref.permit.unmodelled_asset_count
-- @projects   trappoint_ref.permit.unmet_floor_count
-- @projects   trappoint_ref.permit.countersigned_count
-- @projects   trappoint_ref.permit.site_role
-- @on_missing raise
-- @maintained-by the projection band (functions 0100-0109, triggers 0120-0129)
--
-- These are rendered SQL comments and NOT template pragmas, and the difference is
-- deliberate. The Authority Source Contract (rule A-1) requires an [[authority_source]]
-- entry — relation, key, positional columns — behind every pragma'd column. A counter has
-- no such shape: it is an AGGREGATE maintained incrementally from an obligation relation,
-- which the binding declares under [[obligation_source]], not a keyed lookup of one row.
-- Writing the pragma anyway would make `trappoint render` refuse this template for the
-- wrong reason, and would assert in a machine-readable way that a counter is a keyed
-- projection, which it is not. The comment says what is true; the pragma would not.
--
-- ── COLUMN NOTES ─────────────────────────────────────────────────────────────────
-- site_role   denormalised RLS scope token, trigger-filled. §4.1 law 10: an RLS policy
--             expression cannot contain a subquery, so the scope must already be a
--             comparable scalar on the row. NAME rather than STRING because the policy
--             compares it against CURRENT_USER.
-- head_seq    the event chain's head. Derived in-transaction and defended by the CAS on
--             the chain, never by a generator that commits outside the transaction.
-- gate_epoch  increments iff the gate OPENS. The pin's foreign-key target is
--             (permit_id, gate_epoch), so once a completion record exists this column is
--             physically immutable and a new obligation therefore cannot be attached.
-- under_hold  an operational stop that is NOT a gate condition. It is recorded so the
--             console can show it; nothing in this file reads it, on purpose. A hold that
--             silently blocked the merge would be a second, undocumented gate.
-- horizon_at  the permit's own bound. `>=` rather than `>` because opened_at defaults to
--             now() and a caller supplying now() for the horizon in the same statement
--             gets the identical transaction timestamp — a strict comparison would refuse
--             a correct write for a reason that has nothing to do with safety.
--
-- ── NO ON DELETE CASCADE, ANYWHERE ───────────────────────────────────────────────
-- The parent link is RESTRICT in both directions. A cascade rewrites history, which is
-- the precise offence this substrate exists to detect. `permit_parent_not_self` is the
-- other half: the declared remedy for a post-completion fact is a FORK — suspend the
-- issued permit and open a CHILD whose gate is cleared afresh — and a permit that is its
-- own parent is a fork that forked nothing.

CREATE TABLE trappoint_ref.permit (
  permit_id              UUID NOT NULL DEFAULT gen_random_uuid(),
  site_id                UUID NOT NULL,
  site_role              NAME NOT NULL,
  external_ref           STRING NOT NULL,
  ref_name               STRING NOT NULL,
  parent_permit_id       UUID NULL,
  state                  trappoint_ref.subject_state NOT NULL DEFAULT 'draft',
  head_seq               INT8 NOT NULL DEFAULT 0,
  gate_epoch             INT8 NOT NULL DEFAULT 0,
  merged_commit          BYTES NULL,
  under_hold             BOOL NOT NULL DEFAULT false,
  slice_digest           BYTES NULL,
  opened_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
  horizon_at             TIMESTAMPTZ NOT NULL,

  -- ▼▼ PROJECTED CROSS-ROW FACTS. Trigger-written, never supplied. ▼▼
  open_blocking          INT8 NOT NULL DEFAULT 0,
  open_residue           INT8 NOT NULL DEFAULT 0,
  open_conflicts         INT8 NOT NULL DEFAULT 0,
  open_warrants          INT8 NOT NULL DEFAULT 0,
  unmodelled_asset_count INT8 NOT NULL DEFAULT 0,
  unmet_floor_count      INT8 NOT NULL DEFAULT 0,
  countersigned_count    INT8 NOT NULL DEFAULT 0,
  -- ▲▲

  CONSTRAINT ctr_nonneg CHECK (
    open_blocking >= 0 AND
    open_residue >= 0 AND
    open_conflicts >= 0 AND
    open_warrants >= 0 AND
    unmodelled_asset_count >= 0 AND
    unmet_floor_count >= 0 AND
    countersigned_count >= 0
  ),

  -- ▼▼ THE PRODUCT. 7 independent refusals; each name is the exhibit. ▼▼
  CONSTRAINT gate_closed_when_issued        CHECK (state <> 'merged' OR open_blocking = 0),
  CONSTRAINT identity_conserved_when_issued CHECK (state <> 'merged' OR open_residue = 0),
  CONSTRAINT conflicts_resolved_when_issued CHECK (state <> 'merged' OR open_conflicts = 0),
  CONSTRAINT no_open_warrant_when_issued    CHECK (state <> 'merged' OR open_warrants = 0),
  CONSTRAINT boundary_certified_when_issued CHECK (state <> 'merged' OR unmodelled_asset_count = 0),
  CONSTRAINT reading_floor_when_issued
      CHECK (state <> 'merged'
             OR unmet_floor_count = 0
             OR countersigned_count > 0),
  CONSTRAINT merge_evidence                 CHECK (state <> 'merged' OR merged_commit IS NOT NULL),
  -- ▲▲

  CONSTRAINT permit_ledger_nonneg       CHECK (head_seq >= 0 AND gate_epoch >= 0),
  CONSTRAINT permit_external_ref_stated CHECK (external_ref <> ''),
  CONSTRAINT permit_ref_name_stated     CHECK (ref_name <> ''),
  CONSTRAINT permit_site_role_stated    CHECK (site_role <> ''),
  CONSTRAINT permit_horizon_bounded     CHECK (horizon_at >= opened_at),
  CONSTRAINT permit_commit_sized        CHECK (merged_commit IS NULL OR length(merged_commit) = 32),
  CONSTRAINT permit_slice_digest_sized  CHECK (slice_digest IS NULL OR length(slice_digest) = 32),
  CONSTRAINT permit_parent_not_self
    CHECK (parent_permit_id IS NULL OR parent_permit_id <> permit_id),
  CONSTRAINT fk_parent_permit FOREIGN KEY (parent_permit_id)
    REFERENCES trappoint_ref.permit (permit_id)
    ON UPDATE RESTRICT ON DELETE RESTRICT,
  CONSTRAINT pk_permit PRIMARY KEY (permit_id),
  -- The epoch pin's foreign-key target. Without this UNIQUE the pin cannot be declared,
  -- and without the pin a precursor arriving after the merge is a perfectly serializable
  -- history that quietly reopens an issued permit (anomaly A2).
  CONSTRAINT permit_epoch_target        UNIQUE (permit_id, gate_epoch),
  CONSTRAINT permit_external_ref_unique UNIQUE (site_id, external_ref)
);
